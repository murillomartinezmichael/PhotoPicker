"""Aries Outdoor Living — 1 before + 1 during + 1 after + top 6 others."""
from __future__ import annotations

from pathlib import Path

from ..classifier import Classifier, classify_batch
from ..scoring import composite_score
from .registry import Profile, Selection, register_profile

STAGE_LABELS: dict[str, str] = {
    "before": "a bare backyard with no deck or outdoor structure built yet",
    "during": "a partially constructed deck or outdoor structure with framing and lumber visible",
    "after": "a fully finished outdoor deck or screened porch with furniture and finishing touches",
}

# Aesthetic bonus: photos with warm wood tones + natural light score higher.
# Aries's brand is warm cedar / dusk / string lights, not cold overcast midday.
WARMTH_LABEL = "a warm-toned wooden deck at golden hour with natural light and dusk sky"
WARMTH_WEIGHT = 0.5  # boosts quality by up to 50% when warmth is 1.0

# Aesthetic bonus: Aries sells "outdoor living," not "wooden platform on dirt."
# A finished deck framed by mature plants / gardens / hedges reads as the
# integrated-with-nature lifestyle they market. Weighted below WARMTH so
# golden-hour still dominates the direct tiebreaker — greenery is orthogonal
# (a midday shot with lush landscaping still gets the bump).
GREENERY_LABEL = "an outdoor deck surrounded by lush green plants gardens shrubs and mature landscaping"
GREENERY_WEIGHT = 0.2

# Aesthetic bonus: the money shot after dark — string lights, lanterns, an
# illuminated deck at dusk/night reads as "we actually live out here." Distinct
# from WARMTH (golden-hour daylight) and GREENERY (plants). Small weight so it
# stays a tiebreaker under the two primary aesthetics; without a cap on stack
# size a night-lit + warm + green shot would blow past 1.85× baseline quality.
AMBIENT_LIGHTS_LABEL = "an outdoor deck at dusk or night illuminated by string lights lanterns or ambient lighting creating a cozy evening scene"
AMBIENT_LIGHTS_WEIGHT = 0.15

OTHERS_COUNT = 6


def _combined(
    quality: float,
    warmth: float,
    greenery: float = 0.0,
    ambient: float = 0.0,
) -> float:
    """Quality with warmth + greenery + ambient bonuses stacked additively inside the multiplier."""
    return quality * (
        1.0
        + WARMTH_WEIGHT * warmth
        + GREENERY_WEIGHT * greenery
        + AMBIENT_LIGHTS_WEIGHT * ambient
    )


def select(paths: list[Path], classifier: Classifier) -> Selection:
    stage_label_list = list(STAGE_LABELS.values())
    label_to_stage = {v: k for k, v in STAGE_LABELS.items()}
    all_labels = stage_label_list + [WARMTH_LABEL, GREENERY_LABEL, AMBIENT_LIGHTS_LABEL]

    all_probs = classify_batch(classifier, paths, all_labels)
    enriched: list[dict] = []
    for path in paths:
        probs = all_probs[path]
        stage_probs = {
            label_to_stage[label]: prob
            for label, prob in probs.items()
            if label in label_to_stage
        }
        best_stage = max(stage_probs, key=lambda s: stage_probs[s])
        warmth = probs.get(WARMTH_LABEL, 0.0)
        greenery = probs.get(GREENERY_LABEL, 0.0)
        ambient = probs.get(AMBIENT_LIGHTS_LABEL, 0.0)
        quality = composite_score(path)
        enriched.append(
            {
                "path": path,
                "stage_probs": stage_probs,
                "best_stage": best_stage,
                "quality": quality,
                "warmth": warmth,
                "greenery": greenery,
                "ambient": ambient,
                "combined": _combined(quality, warmth, greenery, ambient),
            }
        )

    used: set[Path] = set()
    chosen: dict[str, list[Path]] = {"before": [], "during": [], "after": []}

    for stage in ("before", "during", "after"):
        primary = [d for d in enriched if d["best_stage"] == stage and d["path"] not in used]
        candidates = primary or [d for d in enriched if d["path"] not in used]
        if not candidates:
            continue
        winner = max(candidates, key=lambda d: (d["stage_probs"][stage], d["combined"]))
        chosen[stage].append(winner["path"])
        used.add(winner["path"])

    remaining = [d for d in enriched if d["path"] not in used]
    remaining.sort(key=lambda d: d["combined"], reverse=True)
    chosen["others"] = [d["path"] for d in remaining[:OTHERS_COUNT]]

    return Selection(categorized=chosen)


register_profile(Profile(name="aries", select=select))
