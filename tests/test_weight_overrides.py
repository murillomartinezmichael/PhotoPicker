"""`--weight NAME=VALUE` — retune a profile's rule weights for one run.

The aesthetic weights were compile-time constants: making a shoot lean harder on
golden hour, or ignoring "furnished" for a deck with no staging yet, meant
editing `aries.py`. These tests pin the override contract: the weight the ranker
uses is the overridden one, `--benchmark` reports the overridden one (the table
and the ranking must never disagree), and a typo'd rule name fails loudly rather
than silently tuning nothing.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from photopicker.classifier import StubClassifier
from photopicker.cli import _parse_weights, main
from photopicker.profiles import (
    clear_weight_overrides,
    get_profile,
    known_rule_names,
    set_weight_overrides,
    weight_overrides,
)
from photopicker.profiles.aesthetics import MAX_BONUS
from photopicker.profiles.aries import STAGE_LABELS, WARMTH_LABEL, WARMTH_WEIGHT


@pytest.fixture(autouse=True)
def _no_leaked_overrides():
    """Overrides are process-global (the CLI is one-shot). Tests are not."""
    clear_weight_overrides()
    yield
    clear_weight_overrides()


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    folder = tmp_path / "photos"
    folder.mkdir()
    arr = np.full((256, 256, 3), 128, dtype=np.uint8)
    arr[::16] = 255  # some edges so sharpness > 0
    for i in range(3):
        Image.fromarray(arr).save(folder / f"img_{i:02d}.png")
    return folder


def test_profiles_register_their_rule_names_on_import():
    assert {"warmth", "greenery", "furnished"} <= known_rule_names()
    assert {"people", "clean-lines", "hero-exterior"} <= known_rule_names()


def test_override_changes_the_score_the_profile_ranks_with(photos: Path):
    paths = sorted(photos.iterdir())
    scores = {paths[0].name: {STAGE_LABELS["after"]: 0.9, WARMTH_LABEL: 1.0}}

    before = get_profile("aries").select(paths, StubClassifier(scores=scores))
    baseline = before.explain[paths[0]]

    set_weight_overrides({"warmth": WARMTH_WEIGHT * 2})
    after = get_profile("aries").select(paths, StubClassifier(scores=scores))
    tuned = after.explain[paths[0]]

    assert tuned.quality == pytest.approx(baseline.quality), "base quality is untouched"
    assert tuned.contributions["warmth"] > baseline.contributions["warmth"]
    assert tuned.total > baseline.total
    # The benchmark table still sums to the number it ranked with...
    assert tuned.total == pytest.approx(
        tuned.quality + sum(tuned.contributions.values())
    )
    # ...and an override cannot spend past the stack's saturation ceiling.
    assert tuned.total <= tuned.quality * (1 + MAX_BONUS) + 1e-9


def test_zero_weight_switches_a_rule_off_but_keeps_it_in_the_table(photos: Path):
    paths = sorted(photos.iterdir())
    scores = {paths[0].name: {STAGE_LABELS["after"]: 0.9, WARMTH_LABEL: 1.0}}

    set_weight_overrides({"warmth": 0.0})
    sel = get_profile("aries").select(paths, StubClassifier(scores=scores))
    breakdown = sel.explain[paths[0]]

    assert breakdown.contributions["warmth"] == pytest.approx(0.0)
    assert "warmth" in breakdown.contributions, "a disabled rule is still reported"


def test_clearing_overrides_restores_the_declared_weights():
    set_weight_overrides({"warmth": 0.9})
    assert weight_overrides() == {"warmth": 0.9}
    clear_weight_overrides()
    assert weight_overrides() == {}


def test_unknown_rule_name_is_rejected():
    with pytest.raises(ValueError, match="unknown rule name"):
        set_weight_overrides({"wrmth": 0.9})
    assert weight_overrides() == {}, "a bad batch is not partially applied"


def test_negative_weight_is_rejected():
    with pytest.raises(ValueError, match="must be >= 0"):
        set_weight_overrides({"warmth": -0.2})


@pytest.mark.parametrize(
    "pairs,expected",
    [
        (("warmth=0.8",), {"warmth": 0.8}),
        (("warmth=0", "furnished=1"), {"warmth": 0.0, "furnished": 1.0}),
        ((" warmth = 0.5 ",), {"warmth": 0.5}),
    ],
)
def test_parse_weights_accepts_name_equals_value(pairs, expected):
    assert _parse_weights(pairs) == expected


@pytest.mark.parametrize("pair", ["warmth", "=0.5", "warmth=high"])
def test_parse_weights_rejects_malformed_pairs(pair):
    with pytest.raises(ValueError):
        _parse_weights((pair,))


def test_cli_weight_flag_moves_the_benchmark_table(photos: Path):
    runner = CliRunner()
    args = ["--folder", str(photos), "--profile", "aries", "--benchmark", "--dry-run"]

    plain = runner.invoke(main, args)
    tuned = runner.invoke(main, [*args, "--weight", "warmth=0.0"])

    assert plain.exit_code == 0, plain.output
    assert tuned.exit_code == 0, tuned.output
    assert "+ warmth" in plain.output
    assert plain.output != tuned.output, "the printed contributions must react"


def test_cli_rejects_a_typo_instead_of_silently_ignoring_it(photos: Path):
    result = CliRunner().invoke(
        main,
        [
            "--folder", str(photos),
            "--profile", "aries",
            "--dry-run",
            "--weight", "wrmth=0.9",
        ],
    )
    assert result.exit_code == 1
    assert "unknown rule name" in result.output
