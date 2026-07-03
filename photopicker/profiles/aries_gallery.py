"""Aries — full portfolio gallery batch.

Different job than the `aries` profile (which picks 9 hero-ish frames). This
one takes an entire raw folder — mixed HEIC/JPG, some blurry, some near-dupes —
and produces the per-phase lists that go straight into a project detail page:
before, during, after (each capped at N).

Pipeline:
    twin dedup  ->  perceptual dedup  ->  quality gate  ->  phase classify
    ->  per-phase rank by (phase confidence * quality)  ->  cap
    ->  sort each phase chronologically for storytelling flow
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ..classifier import Classifier, classify_batch
from ..dedup import dedup_all
from ..exif import get_capture_time
from ..quality_gate import filter_usable
from ..scoring import composite_score
from .registry import Profile, Selection, register_profile

STAGE_LABELS: dict[str, str] = {
    "before": "a bare backyard with no deck or outdoor structure built yet",
    "during": "a partially constructed deck or outdoor structure with framing and lumber visible",
    "after": "a fully finished outdoor deck or screened porch with furniture and finishing touches",
}

PER_PHASE_CAP = 8
# EXIF-less photos sort after EXIF'd ones, in stable filename order.
_UNDATED_SENTINEL = datetime.max


def _chronological_key(path: Path) -> tuple[datetime, str]:
    return (get_capture_time(path) or _UNDATED_SENTINEL, path.name)


def select(paths: list[Path], classifier: Classifier) -> Selection:
    original = list(paths)

    # 1. Twin + perceptual dedup — cheap and highest-impact.
    deduped = dedup_all(original)
    twin_and_dup_rejects = [p for p in original if p not in set(deduped)]

    # 2. Reject unreadable / too-small / blurry.
    usable, gate_results = filter_usable(deduped)
    unreadable = [r.path for r in gate_results if not r.kept and r.reason == "unreadable"]
    too_small = [r.path for r in gate_results if not r.kept and r.reason.startswith("too small")]
    blurry = [r.path for r in gate_results if not r.kept and r.reason.startswith("blurry")]

    # 3. Classify each survivor by phase (batched — one forward pass over the folder).
    label_list = list(STAGE_LABELS.values())
    label_to_stage = {v: k for k, v in STAGE_LABELS.items()}
    all_probs = classify_batch(classifier, usable, label_list)
    enriched: list[dict] = []
    for path in usable:
        probs = all_probs[path]
        stage_probs = {label_to_stage[label]: prob for label, prob in probs.items()}
        best_stage = max(stage_probs, key=lambda s: stage_probs[s])
        enriched.append(
            {
                "path": path,
                "stage_probs": stage_probs,
                "best_stage": best_stage,
                "quality": composite_score(path),
            }
        )

    # 4. Per-phase: rank by (phase confidence * quality), cap, then chronological.
    chosen: dict[str, list[Path]] = {"before": [], "during": [], "after": []}
    for stage in ("before", "during", "after"):
        bucket = [d for d in enriched if d["best_stage"] == stage]
        bucket.sort(
            key=lambda d: d["stage_probs"][stage] * (0.5 + d["quality"]),
            reverse=True,
        )
        top = [d["path"] for d in bucket[:PER_PHASE_CAP]]
        # Storytelling flow: within each phase, oldest first.
        chosen[stage] = sorted(top, key=_chronological_key)

    return Selection(
        categorized=chosen,
        rejected={
            "duplicates": twin_and_dup_rejects,
            "unreadable": unreadable,
            "too_small": too_small,
            "blurry": blurry,
        },
    )


register_profile(Profile(name="aries-gallery", select=select))
