"""General-purpose cull pipeline — no themes, no CLIP, just quality.

Different job than the profile system: profiles pick *themed* sets (aries
before/during/after, big7 repair/build). `cull` is what you want when a client
hands you a raw 500-photo folder and you need to hand back the 30 best. Fully
offline, deterministic, dep-light (no torch, no CLIP), fast enough that AI
rerank feels like a bonus and not the point.

Pipeline (revised 2026-07-05 for sharpest-per-cluster):
    twin collapse (metadata) -> composite score (one pass over every survivor)
    -> sort by score DESC -> perceptual dedup (first-seen = highest-scored
    per cluster) -> quality gate (unreadable/tiny/blurry) -> top N.

Sort-by-score BEFORE perceptual dedup is the whole quality win: when a burst
of 6 near-identical frames comes through, we keep the sharpest, not just the
first one iOS happened to emit.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .dedup import collapse_heic_jpg_twins, dedup_perceptual_clusters
from .exif import get_capture_time
from .quality_gate import filter_usable
from .scoring import composite_score

DEFAULT_TOP_N = 30
DEFAULT_MIN_SHARPNESS = 60.0
DEFAULT_MIN_LONG_EDGE = 800

SORT_MODES = ("score", "capture-time", "name")

Progress = Callable[[str, int, int], None]


@dataclass
class CullResult:
    keepers: list[Path]
    scores: dict[Path, float]
    rejected: dict[str, list[Path]] = field(default_factory=dict)
    input_count: int = 0
    # winner -> near-duplicate frames that lost to it (perceptual dedup). The
    # frames themselves never enter `keepers`/`scores` — that contract is
    # keepers-only. Their scores live in `all_scores` so a reviewer can still
    # see them (burst compare / swap-the-pick) without the public result
    # shape changing shape depending on whether a cull had bursts in it.
    clusters: dict[Path, list[Path]] = field(default_factory=dict)
    # Every scored survivor (pre quality-gate, pre top-N), keepers included.
    # Lets consumers look up a cluster member's score without it being a
    # "kept" photo.
    all_scores: dict[Path, float] = field(default_factory=dict)

    @property
    def total_input(self) -> int:
        return self.input_count

    def reject_counts(self) -> dict[str, int]:
        return {r: len(ps) for r, ps in self.rejected.items() if ps}

    def all_rejected(self) -> list[Path]:
        seen: set[Path] = set()
        out: list[Path] = []
        for paths in self.rejected.values():
            for p in paths:
                if p not in seen:
                    out.append(p)
                    seen.add(p)
        return out

    def summary(self) -> str:
        lines = [
            f"Culled {self.input_count} -> {len(self.keepers)}",
            "",
            "Top keepers (score):",
        ]
        for rank, path in enumerate(self.keepers, start=1):
            score = self.scores.get(path, 0.0)
            lines.append(f"  {rank:>2}. {path.name:<40} {score:.3f}")
        rc = self.reject_counts()
        if rc:
            lines.append("")
            lines.append("Rejected:")
            for reason, count in rc.items():
                lines.append(f"  - {reason}: {count}")
        return "\n".join(lines)


def cull(
    paths: list[Path],
    top_n: int = DEFAULT_TOP_N,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
    min_long_edge: int = DEFAULT_MIN_LONG_EDGE,
    sort: str = "score",
    progress: Progress | None = None,
    face_gate: bool = False,
) -> CullResult:
    """Cull `paths` down to the top `top_n` keepers.

    Progress callback signature: `progress(stage, done, total)`. Stages fire
    in order: `"twin-collapse"`, `"scoring"`, `"faces"` (only when
    `face_gate=True`), `"dedup"`, `"quality-gate"`.

    `sort` selects the final keeper order (does not affect *which* photos win —
    that is always composite score). Options: `score` (default; best first),
    `capture-time` (EXIF, oldest first; falls back to filename when EXIF missing),
    `name` (filename ascending).

    `face_gate` opt-in (default off): multiplies each photo's composite score
    by `faces.face_eye_score()` so a closed-eye portrait ranks below an
    otherwise-equal open-eye frame. Off by default so existing callers see no
    behavior change; requires `pip install "photopicker[faces]"` when enabled
    (raises `ImportError` with the install hint otherwise). Photos with no
    detected face are unaffected (neutral 1.0 multiplier).
    """
    if sort not in SORT_MODES:
        raise ValueError(f"sort={sort!r} not one of {SORT_MODES}")

    original = list(paths)
    n = len(original)
    if progress:
        progress("twin-collapse", 0, n)
    twin_collapsed = collapse_heic_jpg_twins(original)
    twin_dropped = [p for p in original if p not in set(twin_collapsed)]
    if progress:
        progress("twin-collapse", n, n)

    # Score every survivor once — cached and reused for dedup + rank.
    if progress:
        progress("scoring", 0, len(twin_collapsed))
    scores: dict[Path, float] = {}
    for i, p in enumerate(twin_collapsed, start=1):
        scores[p] = composite_score(p)
        if progress and (i % 20 == 0 or i == len(twin_collapsed)):
            progress("scoring", i, len(twin_collapsed))

    if face_gate:
        from .faces import face_eye_score

        if progress:
            progress("faces", 0, len(twin_collapsed))
        for i, p in enumerate(twin_collapsed, start=1):
            scores[p] *= face_eye_score(p).score
            if progress and (i % 20 == 0 or i == len(twin_collapsed)):
                progress("faces", i, len(twin_collapsed))

    # Perceptual dedup on the score-sorted list: highest-scored wins its cluster.
    by_score_desc = sorted(twin_collapsed, key=lambda p: scores[p], reverse=True)
    if progress:
        progress("dedup", 0, len(by_score_desc))
    deduped, clusters = dedup_perceptual_clusters(by_score_desc)
    perceptual_dropped = [p for p in twin_collapsed if p not in set(deduped)]
    if progress:
        progress("dedup", len(by_score_desc), len(by_score_desc))

    # Quality gate on survivors only — saves us re-reading rejects.
    if progress:
        progress("quality-gate", 0, len(deduped))
    usable, gate_results = filter_usable(
        deduped, min_sharpness=min_sharpness, min_long_edge=min_long_edge
    )
    unreadable = [r.path for r in gate_results if not r.kept and r.reason == "unreadable"]
    too_small = [r.path for r in gate_results if not r.kept and r.reason.startswith("too small")]
    blurry = [r.path for r in gate_results if not r.kept and r.reason.startswith("blurry")]
    if progress:
        progress("quality-gate", len(deduped), len(deduped))

    # Take top N by score (that is what the operator asked for — quality first).
    usable_by_score = sorted(usable, key=lambda p: scores[p], reverse=True)
    winners = usable_by_score[:top_n]

    # Only reorder for presentation; scoring truth stays the same.
    keepers = _order_keepers(winners, scores, sort)
    keeper_scores = {p: scores[p] for p in keepers}

    duplicates = _dedupe_paths([*twin_dropped, *perceptual_dropped])

    return CullResult(
        keepers=keepers,
        scores=keeper_scores,
        rejected={
            "duplicates": duplicates,
            "unreadable": unreadable,
            "too_small": too_small,
            "blurry": blurry,
        },
        input_count=n,
        clusters=clusters,
        all_scores=scores,
    )


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    out: list[Path] = []
    for p in paths:
        if p not in seen:
            out.append(p)
            seen.add(p)
    return out


def _order_keepers(
    winners: list[Path],
    scores: dict[Path, float],
    sort: str,
) -> list[Path]:
    if sort == "score":
        return list(winners)
    if sort == "name":
        return sorted(winners, key=lambda p: p.name.lower())
    # capture-time: EXIF ascending; missing EXIF sorts after (datetime.max sentinel)
    # and then by filename for stability.
    def _key(p: Path):
        capture = get_capture_time(p)
        return (capture or datetime.max, p.name.lower())
    return sorted(winners, key=_key)
