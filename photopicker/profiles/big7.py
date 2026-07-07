"""Big7 Construction — splits photos into repair vs new-build buckets, top 6 each."""
from __future__ import annotations

from pathlib import Path

from ..classifier import Classifier, classify_batch
from ..scoring import composite_score
from .registry import Profile, Selection, register_profile

CATEGORY_LABELS: dict[str, str] = {
    "repair": "an interior or exterior home repair or restoration job in progress or finished",
    "build": "a new home construction site or freshly built house exterior",
}

# Aesthetic bonus: Big7's brand shows real crews on real sites, not empty rooms.
# A photo with visible people + a construction element (framing, tools, ladders,
# freshly poured concrete) beats a same-quality shot of the same wall with no one in it.
PEOPLE_LABEL = "construction workers in frame on a jobsite with tools framing or equipment visible"
PEOPLE_WEIGHT = 0.5  # boosts quality by up to 50% when people prob is 1.0

PER_BUCKET = 6


def _combined(quality: float, people: float) -> float:
    """Quality with a people-on-site bonus. Helper so tests can pin the math."""
    return quality * (1.0 + PEOPLE_WEIGHT * people)


def select(paths: list[Path], classifier: Classifier) -> Selection:
    category_list = list(CATEGORY_LABELS.values())
    label_to_cat = {v: k for k, v in CATEGORY_LABELS.items()}
    all_labels = category_list + [PEOPLE_LABEL]

    all_probs = classify_batch(classifier, paths, all_labels)
    buckets: dict[str, list[tuple[Path, float]]] = {cat: [] for cat in CATEGORY_LABELS}
    for path in paths:
        probs = all_probs[path]
        cat_probs = {label: probs[label] for label in category_list}
        best_label = max(cat_probs, key=lambda label: cat_probs[label])
        cat = label_to_cat[best_label]
        quality = composite_score(path)
        people = probs.get(PEOPLE_LABEL, 0.0)
        buckets[cat].append((path, _combined(quality, people)))

    out: dict[str, list[Path]] = {}
    for cat, items in buckets.items():
        items.sort(key=lambda x: x[1], reverse=True)
        out[cat] = [p for p, _ in items[:PER_BUCKET]]
    return Selection(categorized=out)


register_profile(Profile(name="big7", select=select))
