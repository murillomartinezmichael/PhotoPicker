"""A `--config` JSON profile can declare its own tunable aesthetic rules.

Before the `rules` key, a config profile ranked on bare quality and had no rule
names, so `--benchmark` had nothing to print and `--weight` was a hard error. A
new site can now be onboarded *and* tuned without a Python file.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from photopicker import cli as cli_module
from photopicker.classifier import StubClassifier
from photopicker.profiles import ConfigError, build_from_config
from photopicker.profiles.aesthetics import clear_weight_overrides

PHASES = {"empty": "an empty room", "done": "a finished furnished room"}
WARM_LABEL = "a warm-toned room at golden hour"

BASE_CFG = {
    "name": "ruled",
    "phases": PHASES,
    "chronological": False,
    "per_phase_cap": 10,
}


@pytest.fixture(autouse=True)
def _no_leaked_weight_overrides():
    """`--weight` writes process-global state; a leak would retune 'aries' warmth."""
    yield
    clear_weight_overrides()


def _cfg(**overrides) -> dict:
    return {**BASE_CFG, **overrides}


def _scores(paths: list[Path], warm: Path | None, warm_prob: float = 1.0) -> dict:
    """Every photo lands in 'done' with equal confidence; only `warm` trips the rule."""
    return {
        p.name: {
            PHASES["done"]: 0.9,
            PHASES["empty"]: 0.1,
            WARM_LABEL: warm_prob if p == warm else 0.0,
        }
        for p in paths
    }


def test_rules_key_declares_tunable_rule_names():
    profile = build_from_config(
        _cfg(rules=[{"name": "warmth", "label": WARM_LABEL, "weight": 0.5}])
    )
    assert profile.rule_names == frozenset({"warmth"})


def test_no_rules_key_leaves_profile_untunable():
    assert build_from_config(_cfg()).rule_names == frozenset()


def test_rule_bonus_lifts_a_photo_to_the_top_of_its_phase(
    folder_of_distinct_large_images: Path,
):
    """A photo the rule fires on outranks the ones it doesn't, quality being close.

    `max_bonus` 3.0 with a weight of 3.0 means a full-probability hit scores 4x
    bare quality — far more than the fixture images differ from each other, so
    the assertion tests the rule, not the noise in composite_score.
    """
    paths = sorted(folder_of_distinct_large_images.iterdir())
    boosted = paths[-1]
    profile = build_from_config(
        _cfg(
            max_bonus=3.0,
            rules=[{"name": "warmth", "label": WARM_LABEL, "weight": 3.0}],
        )
    )

    sel = profile.select(paths, StubClassifier(scores=_scores(paths, boosted)))

    assert sel.categorized["done"][0] == boosted
    breakdown = sel.explain[boosted]
    assert breakdown.contributions["warmth"] == pytest.approx(3.0 * breakdown.quality)
    assert sel.explain[paths[0]].contributions["warmth"] == 0.0


def test_unruled_photo_ranks_on_bare_quality(folder_of_distinct_large_images: Path):
    """A rule that fires nowhere leaves the ranking exactly where it was."""
    paths = sorted(folder_of_distinct_large_images.iterdir())
    ruled = build_from_config(
        _cfg(rules=[{"name": "warmth", "label": WARM_LABEL, "weight": 0.5}])
    )
    plain = build_from_config(_cfg())
    scores = _scores(paths, warm=None)

    ruled_order = ruled.select(paths, StubClassifier(scores=scores)).categorized["done"]
    plain_order = plain.select(paths, StubClassifier(scores=scores)).categorized["done"]
    assert ruled_order == plain_order


def test_bonus_saturates_at_max_bonus(folder_of_distinct_large_images: Path):
    """Two big rules both firing still top out at the stack ceiling, not 2x it."""
    paths = sorted(folder_of_distinct_large_images.iterdir())
    other_label = "a second aesthetic"
    profile = build_from_config(
        _cfg(
            rules=[
                {"name": "warmth", "label": WARM_LABEL, "weight": 0.6},
                {"name": "other", "label": other_label, "weight": 0.6},
            ]
        )
    )
    scores = {p.name: {**_scores(paths, p)[p.name], other_label: 1.0} for p in paths}

    sel = profile.select(paths, StubClassifier(scores=scores))
    breakdown = sel.explain[paths[0]]
    # Both rules fire fully (1.2 raw) but the default 0.75 ceiling holds.
    assert sum(breakdown.contributions.values()) == pytest.approx(
        0.75 * breakdown.quality
    )


@pytest.mark.parametrize(
    "rules, message",
    [
        ([], "non-empty list"),
        ("warmth", "non-empty list"),
        (["warmth"], "must be an object"),
        ([{"label": WARM_LABEL, "weight": 0.5}], "non-empty 'name'"),
        ([{"name": "warmth", "weight": 0.5}], "non-empty 'label'"),
        ([{"name": "warmth", "label": WARM_LABEL}], "numeric 'weight'"),
        ([{"name": "warmth", "label": WARM_LABEL, "weight": "hot"}], "numeric 'weight'"),
        ([{"name": "warmth", "label": WARM_LABEL, "weight": -1}], "must be >= 0"),
        (
            [
                {"name": "warmth", "label": WARM_LABEL, "weight": 0.5},
                {"name": "warmth", "label": "another", "weight": 0.2},
            ],
            "duplicate rule name",
        ),
    ],
)
def test_malformed_rules_raise_config_error(rules, message):
    with pytest.raises(ConfigError, match=message):
        build_from_config(_cfg(rules=rules))


@pytest.mark.parametrize("max_bonus", ["big", -0.5])
def test_bad_max_bonus_raises_config_error(max_bonus):
    with pytest.raises(ConfigError, match="max_bonus"):
        build_from_config(
            _cfg(
                max_bonus=max_bonus,
                rules=[{"name": "warmth", "label": WARM_LABEL, "weight": 0.5}],
            )
        )


def _patch_cli_classifier(monkeypatch):
    original = cli_module.pick_photos

    def patched(folder, profile_name, classifier=None):
        paths = sorted(p for p in Path(folder).iterdir() if p.is_file())
        stub = StubClassifier(scores=_scores(paths, warm=paths[-1]))
        return original(folder, profile_name, classifier=classifier or stub)

    monkeypatch.setattr(cli_module, "pick_photos", patched)


def test_cli_weight_tunes_a_config_profile_rule(
    folder_of_distinct_large_images: Path, tmp_path: Path, monkeypatch
):
    """The payoff: `--weight` on a config profile now retunes instead of erroring."""
    _patch_cli_classifier(monkeypatch)
    cfg_path = tmp_path / "profile.json"
    cfg_path.write_text(
        json.dumps(_cfg(rules=[{"name": "warmth", "label": WARM_LABEL, "weight": 0.5}])),
        encoding="utf-8",
    )

    result = CliRunner().invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_distinct_large_images),
            "--config", str(cfg_path),
            "--dry-run", "--benchmark",
            "--weight", "warmth=0.9",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "warmth" in result.output


def test_cli_weight_on_ruleless_config_profile_still_errors(
    folder_of_distinct_large_images: Path, tmp_path: Path, monkeypatch
):
    _patch_cli_classifier(monkeypatch)
    cfg_path = tmp_path / "plain.json"
    cfg_path.write_text(json.dumps(_cfg()), encoding="utf-8")

    result = CliRunner().invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_distinct_large_images),
            "--config", str(cfg_path),
            "--dry-run",
            "--weight", "warmth=0.9",
        ],
    )

    assert result.exit_code == 1
    assert "no tunable rules" in result.output
