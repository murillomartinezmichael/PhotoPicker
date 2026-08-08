from __future__ import annotations

import pytest

from photopicker.profiles import aries, big7
from photopicker.profiles.aesthetics import MAX_BONUS, AestheticRule, AestheticRules

RULES = AestheticRules(
    [
        AestheticRule("warm", "a warm photo", 0.5),
        AestheticRule("green", "a green photo", 0.2),
    ]
)

# Weights sum to 1.2 — over the 0.75 ceiling, so this stack saturates when it
# fires hard. Mirrors what the shipped profiles do at full probability.
GREEDY = AestheticRules(
    [
        AestheticRule("warm", "a warm photo", 0.8),
        AestheticRule("green", "a green photo", 0.4),
    ]
)


def test_labels_are_the_clip_prompts_in_declaration_order():
    assert RULES.labels == ["a warm photo", "a green photo"]


def test_contribution_is_weight_times_probability_times_quality():
    contrib = RULES.contributions(10.0, {"a warm photo": 0.5, "a green photo": 1.0})
    assert contrib == {"warm": 2.5, "green": 2.0}


def test_rules_that_did_not_fire_stay_in_the_table_at_zero():
    # --benchmark shows every rule the profile considered, not just the hits.
    contrib = RULES.contributions(10.0, {"a warm photo": 1.0})
    assert contrib == {"warm": 5.0, "green": 0.0}


def test_bonuses_stack_additively_on_top_of_base_quality():
    combined = RULES.combined(10.0, {"a warm photo": 1.0, "a green photo": 1.0})
    assert combined == pytest.approx(10.0 * (1 + 0.5 + 0.2))


def test_no_rule_fires_leaves_quality_untouched():
    assert RULES.combined(7.5, {}) == pytest.approx(7.5)


def test_breakdown_total_equals_the_ranking_score():
    # The invariant this module exists to enforce: the number --benchmark prints
    # and the number the profile ranks with are the same number, by construction.
    probs = {"a warm photo": 0.3, "a green photo": 0.9}
    assert RULES.breakdown(12.0, probs).total == pytest.approx(RULES.combined(12.0, probs))


@pytest.mark.parametrize("profile", [aries, big7], ids=["aries", "big7"])
def test_shipped_profiles_rank_with_their_own_benchmark_table(profile):
    # Every real rule at full probability — the ranker and the explanation must agree.
    probs = {rule.label: 1.0 for rule in profile.RULES.rules}
    breakdown = profile.RULES.breakdown(4.0, probs)
    assert breakdown.total == pytest.approx(profile.RULES.combined(4.0, probs))
    assert set(breakdown.contributions) == {rule.name for rule in profile.RULES.rules}


@pytest.mark.parametrize("profile", [aries, big7], ids=["aries", "big7"])
def test_profile_rule_names_and_labels_are_unique(profile):
    rules = profile.RULES.rules
    assert len({r.name for r in rules}) == len(rules)
    assert len({r.label for r in rules}) == len(rules)


@pytest.mark.parametrize(
    ("profile", "cap"),
    [(aries, 0.97), (big7, 1.05)],
    ids=["aries", "big7"],
)
def test_stacked_weights_stay_within_the_documented_cap(profile, cap):
    # A photo that trips every rule must not run away with the ranking; this pins
    # the max multiplier so a future rule can't quietly double it.
    assert sum(r.weight for r in profile.RULES.rules) == pytest.approx(cap)


def test_bonus_saturates_at_the_ceiling():
    # 0.8 + 0.4 = 1.2x earned, but aesthetics may only lift a photo by MAX_BONUS.
    assert GREEDY.combined(10.0, {"a warm photo": 1.0, "a green photo": 1.0}) == (
        pytest.approx(10.0 * (1 + MAX_BONUS))
    )


def test_saturated_contributions_keep_their_relative_shares():
    # Scaling is proportional: warm carries 2/3 of the earned bonus before the cap
    # and still carries 2/3 of it after, so --benchmark keeps telling the truth
    # about which rule did the work.
    contrib = GREEDY.contributions(10.0, {"a warm photo": 1.0, "a green photo": 1.0})
    assert contrib["warm"] == pytest.approx(10.0 * MAX_BONUS * (0.8 / 1.2))
    assert contrib["green"] == pytest.approx(10.0 * MAX_BONUS * (0.4 / 1.2))
    assert sum(contrib.values()) == pytest.approx(10.0 * MAX_BONUS)


def test_breakdown_total_still_equals_the_ranking_score_when_saturated():
    probs = {"a warm photo": 1.0, "a green photo": 1.0}
    assert GREEDY.breakdown(9.0, probs).total == pytest.approx(GREEDY.combined(9.0, probs))


def test_below_the_ceiling_nothing_is_scaled():
    # 0.8 * 0.5 + 0.4 * 0.25 = 0.5 earned — under the cap, so full points stand.
    contrib = GREEDY.contributions(10.0, {"a warm photo": 0.5, "a green photo": 0.25})
    assert contrib == {"warm": pytest.approx(4.0), "green": pytest.approx(1.0)}


def test_saturation_never_reorders_two_photos():
    # The multiplier is min(earned, cap): monotone non-decreasing in earned bonus,
    # so a photo that scores every rule higher can never fall below a weaker one.
    weak = GREEDY.combined(10.0, {"a warm photo": 0.9, "a green photo": 0.9})
    strong = GREEDY.combined(10.0, {"a warm photo": 1.0, "a green photo": 1.0})
    assert strong >= weak


def test_quality_still_outranks_aesthetics_alone():
    # The point of the ceiling: a sharp photo with zero aesthetic signal beats a
    # much softer one that trips every rule at full probability.
    sharp_and_plain = GREEDY.combined(10.0, {})
    soft_and_pretty = GREEDY.combined(5.0, {"a warm photo": 1.0, "a green photo": 1.0})
    assert sharp_and_plain > soft_and_pretty


@pytest.mark.parametrize("profile", [aries, big7], ids=["aries", "big7"])
def test_shipped_profiles_cannot_exceed_the_ceiling(profile):
    probs = {rule.label: 1.0 for rule in profile.RULES.rules}
    assert profile.RULES.combined(8.0, probs) == pytest.approx(8.0 * (1 + MAX_BONUS))
