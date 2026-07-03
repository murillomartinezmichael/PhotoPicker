"""Config-driven profile — new project onboarding without writing Python.

Feed a JSON dict (loaded from disk by the CLI, or built inline in code) and get
back a fully functional `Profile` that runs the same pipeline as
`aries-gallery`:

    twin dedup → perceptual dedup → quality gate → CLIP phase classify
    → per-phase (confidence * quality) rank → cap → chronological

Minimum config:

    {
        "name": "backyard-remodel",
        "phases": {
            "before": "an empty backyard before construction",
            "during": "a partially constructed outdoor structure",
            "after": "a finished backyard with furniture"
        }
    }

Optional keys with defaults:

    "per_phase_cap": 8,
    "chronological": true,
    "quality_gate": {"min_sharpness": 60.0, "min_long_edge": 800},
    "dedup": {"perceptual_threshold": 6}
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ..classifier import Classifier, classify_batch
from ..dedup import DEFAULT_HAMMING_THRESHOLD, dedup_all
from ..exif import get_capture_time
from ..quality_gate import DEFAULT_MIN_LONG_EDGE, DEFAULT_MIN_SHARPNESS, filter_usable
from ..scoring import composite_score
from .registry import Profile, Selection

DEFAULT_PER_PHASE_CAP = 8
_UNDATED_SENTINEL = datetime.max


class ConfigError(ValueError):
    """Raised when a config dict is missing required keys or is malformed."""


def _chronological_key(path: Path) -> tuple[datetime, str]:
    return (get_capture_time(path) or _UNDATED_SENTINEL, path.name)


def _validate(cfg: dict[str, Any]) -> None:
    if "phases" not in cfg or not isinstance(cfg["phases"], dict) or not cfg["phases"]:
        raise ConfigError("config must have a non-empty 'phases' object")
    for k, v in cfg["phases"].items():
        if not isinstance(k, str) or not isinstance(v, str) or not v.strip():
            raise ConfigError(f"phase '{k}' must map to a non-empty description string")


def build_from_config(cfg: dict[str, Any]) -> Profile:
    _validate(cfg)

    name: str = cfg.get("name") or "custom"
    phases: dict[str, str] = dict(cfg["phases"])
    per_phase_cap: int = int(cfg.get("per_phase_cap", DEFAULT_PER_PHASE_CAP))
    chronological: bool = bool(cfg.get("chronological", True))

    gate_cfg = cfg.get("quality_gate") or {}
    min_sharpness = float(gate_cfg.get("min_sharpness", DEFAULT_MIN_SHARPNESS))
    min_long_edge = int(gate_cfg.get("min_long_edge", DEFAULT_MIN_LONG_EDGE))

    dedup_cfg = cfg.get("dedup") or {}
    perceptual_threshold = int(
        dedup_cfg.get("perceptual_threshold", DEFAULT_HAMMING_THRESHOLD)
    )

    label_list = list(phases.values())
    label_to_stage = {v: k for k, v in phases.items()}
    stage_order = list(phases.keys())

    def select(paths: list[Path], classifier: Classifier) -> Selection:
        original = list(paths)

        deduped = dedup_all(original, perceptual_threshold=perceptual_threshold)
        twin_and_dup_rejects = [p for p in original if p not in set(deduped)]

        usable, gate_results = filter_usable(deduped, min_sharpness, min_long_edge)
        unreadable = [
            r.path for r in gate_results if not r.kept and r.reason == "unreadable"
        ]
        too_small = [
            r.path for r in gate_results if not r.kept and r.reason.startswith("too small")
        ]
        blurry = [
            r.path for r in gate_results if not r.kept and r.reason.startswith("blurry")
        ]

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

        chosen: dict[str, list[Path]] = {stage: [] for stage in stage_order}
        for stage in stage_order:
            bucket = [d for d in enriched if d["best_stage"] == stage]
            bucket.sort(
                key=lambda d: d["stage_probs"][stage] * (0.5 + d["quality"]),
                reverse=True,
            )
            top = [d["path"] for d in bucket[:per_phase_cap]]
            if chronological:
                top = sorted(top, key=_chronological_key)
            chosen[stage] = top

        return Selection(
            categorized=chosen,
            rejected={
                "duplicates": twin_and_dup_rejects,
                "unreadable": unreadable,
                "too_small": too_small,
                "blurry": blurry,
            },
        )

    return Profile(name=name, select=select)
