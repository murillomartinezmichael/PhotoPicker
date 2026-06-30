"""Aries Outdoor Living — 1 before + 1 during + 1 after + top 6 others."""
from __future__ import annotations

from pathlib import Path

from ..classifier import Classifier
from ..scoring import composite_score
from .registry import Profile, Selection, register_profile

STAGE_LABELS: dict[str, str] = {
    "before": "a bare backyard with no deck or outdoor structure built yet",
    "during": "a partially constructed deck or outdoor structure with framing and lumber visible",
    "after": "a fully finished outdoor deck or screened porch with furniture and finishing touches",
}

OTHERS_COUNT = 6


def select(paths: list[Path], classifier: Classifier) -> Selection:
    label_list = list(STAGE_LABELS.values())
    label_to_stage = {v: k for k, v in STAGE_LABELS.items()}

    enriched: list[dict] = []
    for path in paths:
        probs = classifier.score(path, label_list)
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

    used: set[Path] = set()
    chosen: dict[str, list[Path]] = {"before": [], "during": [], "after": []}

    for stage in ("before", "during", "after"):
        primary = [d for d in enriched if d["best_stage"] == stage and d["path"] not in used]
        candidates = primary or [d for d in enriched if d["path"] not in used]
        if not candidates:
            continue
        winner = max(candidates, key=lambda d: (d["stage_probs"][stage], d["quality"]))
        chosen[stage].append(winner["path"])
        used.add(winner["path"])

    remaining = [d for d in enriched if d["path"] not in used]
    remaining.sort(key=lambda d: d["quality"], reverse=True)
    chosen["others"] = [d["path"] for d in remaining[:OTHERS_COUNT]]

    return Selection(categorized=chosen)


register_profile(Profile(name="aries", select=select))
