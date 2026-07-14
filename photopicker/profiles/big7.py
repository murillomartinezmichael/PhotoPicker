"""Big7 Construction — splits photos into repair vs new-build buckets, top 6 each."""
from __future__ import annotations

from pathlib import Path

from ..classifier import Classifier, classify_batch
from ..scoring import composite_score
from .aesthetics import AestheticRule, AestheticRules
from .registry import Profile, RuleBreakdown, Selection, register_profile

CATEGORY_LABELS: dict[str, str] = {
    "repair": "an interior or exterior home repair or restoration job in progress or finished",
    "build": "a new home construction site or freshly built house exterior",
}

# Aesthetic bonus: Big7's brand shows real crews on real sites, not empty rooms.
# A photo with visible people + a construction element (framing, tools, ladders,
# freshly poured concrete) beats a same-quality shot of the same wall with no one in it.
PEOPLE_LABEL = "construction workers in frame on a jobsite with tools framing or equipment visible"
PEOPLE_WEIGHT = 0.5  # boosts quality by up to 50% when people prob is 1.0

# Aesthetic bonus: construction is a trade about precision. Shots that show
# straight framing, level surfaces, and square corners read as craftsmanship;
# cluttered handheld angles read as amateur. Weight is smaller than PEOPLE
# so crew-on-site still dominates the ranking — clean-lines is the tiebreaker.
CLEAN_LINES_LABEL = "a well-composed construction photo with clean straight lines square framing and level horizons"
CLEAN_LINES_WEIGHT = 0.3

# Aesthetic bonus: Big7 sells finished work — the "here is what your home
# will look like after we're done" money shot. Photos that read as complete
# (clean surfaces, no debris, no unfinished work) beat mid-repair shots for
# marketing use. Orthogonal to PEOPLE (occupancy) and CLEAN_LINES (composition):
# a completed handover reads as trust regardless of who's in frame. Small
# weight so PEOPLE and CLEAN_LINES still dominate the direct tiebreaker.
FINISHED_RESULT_LABEL = "a completed construction project with clean finished surfaces and no debris or unfinished work visible"
FINISHED_RESULT_WEIGHT = 0.15

# Aesthetic bonus: the residential-GC hero shot — a completed exterior from
# the street showing the whole front elevation with driveway, entry, and
# landscaping. This is the image prospects screenshot and send to their
# spouse; it's the specific "curb appeal" money shot, not just any completion.
# Orthogonal to FINISHED_RESULT (which fires for any completed room too);
# hero-exterior narrows to the street-view sales frame. Small weight — this
# stays a tiebreaker under FINISHED_RESULT so an interior handover shot with
# people still beats a distant empty facade.
HERO_EXTERIOR_LABEL = "the completed exterior front view of a house showing curb appeal driveway front door and landscaping from the street"
HERO_EXTERIOR_WEIGHT = 0.1

PER_BUCKET = 6

# The rule stack. Adding a bonus = one entry here; ranking and the `--benchmark`
# table both read from it, so they cannot drift apart. See `aesthetics.py`.
RULES = AestheticRules(
    [
        AestheticRule("people", PEOPLE_LABEL, PEOPLE_WEIGHT),
        AestheticRule("clean-lines", CLEAN_LINES_LABEL, CLEAN_LINES_WEIGHT),
        AestheticRule("finished-result", FINISHED_RESULT_LABEL, FINISHED_RESULT_WEIGHT),
        AestheticRule("hero-exterior", HERO_EXTERIOR_LABEL, HERO_EXTERIOR_WEIGHT),
    ]
)


def _combined(
    quality: float,
    people: float,
    clean_lines: float = 0.0,
    finished: float = 0.0,
    hero: float = 0.0,
) -> float:
    """Quality with people + clean-lines + finished-result + hero-exterior bonuses stacked."""
    return RULES.combined(
        quality,
        {
            PEOPLE_LABEL: people,
            CLEAN_LINES_LABEL: clean_lines,
            FINISHED_RESULT_LABEL: finished,
            HERO_EXTERIOR_LABEL: hero,
        },
    )


def select(paths: list[Path], classifier: Classifier) -> Selection:
    category_list = list(CATEGORY_LABELS.values())
    label_to_cat = {v: k for k, v in CATEGORY_LABELS.items()}
    all_labels = category_list + RULES.labels

    all_probs = classify_batch(classifier, paths, all_labels)
    buckets: dict[str, list[tuple[Path, float]]] = {cat: [] for cat in CATEGORY_LABELS}
    explain: dict[Path, RuleBreakdown] = {}
    for path in paths:
        probs = all_probs[path]
        cat_probs = {label: probs[label] for label in category_list}
        best_label = max(cat_probs, key=lambda label: cat_probs[label])
        cat = label_to_cat[best_label]
        breakdown = RULES.breakdown(composite_score(path), probs)
        explain[path] = breakdown
        buckets[cat].append((path, breakdown.total))

    out: dict[str, list[Path]] = {}
    for cat, items in buckets.items():
        items.sort(key=lambda x: x[1], reverse=True)
        out[cat] = [p for p, _ in items[:PER_BUCKET]]
    return Selection(categorized=out, explain=explain)


register_profile(Profile(name="big7", select=select))
