"""Big7 Construction — splits photos into repair vs new-build buckets, top 6 each."""
from __future__ import annotations

from pathlib import Path

from ..classifier import Classifier
from ..scoring import composite_score
from .registry import Profile, Selection, register_profile

CATEGORY_LABELS: dict[str, str] = {
    "repair": "an interior or exterior home repair or restoration job in progress or finished",
    "build": "a new home construction site or freshly built house exterior",
}

PER_BUCKET = 6


def select(paths: list[Path], classifier: Classifier) -> Selection:
    label_list = list(CATEGORY_LABELS.values())
    label_to_cat = {v: k for k, v in CATEGORY_LABELS.items()}

    buckets: dict[str, list[tuple[Path, float]]] = {cat: [] for cat in CATEGORY_LABELS}
    for path in paths:
        probs = classifier.score(path, label_list)
        best_label = max(probs, key=lambda label: probs[label])
        cat = label_to_cat[best_label]
        buckets[cat].append((path, composite_score(path)))

    out: dict[str, list[Path]] = {}
    for cat, items in buckets.items():
        items.sort(key=lambda x: x[1], reverse=True)
        out[cat] = [p for p, _ in items[:PER_BUCKET]]
    return Selection(categorized=out)


register_profile(Profile(name="big7", select=select))
