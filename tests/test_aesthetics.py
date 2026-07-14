from __future__ import annotations

import pytest

from photopicker.profiles import aries, big7
from photopicker.profiles.aesthetics import AestheticRule, AestheticRules

RULES = AestheticRules(
    [
        AestheticRule("warm", "a warm photo", 0.5),
        AestheticRule("green", "a green photo", 0.2),
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
    [(aries, 0.85), (big7, 1.05)],
    ids=["aries", "big7"],
)
def test_stacked_weights_stay_within_the_documented_cap(profile, cap):
    # A photo that trips every rule must not run away with the ranking; this pins
    # the max multiplier so a future rule can't quietly double it.
    assert sum(r.weight for r in profile.RULES.rules) == pytest.approx(cap)
