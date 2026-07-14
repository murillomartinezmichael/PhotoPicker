"""`--benchmark` — per-rule score contributions.

The profiles stack aesthetic bonuses (warmth, greenery, people, clean-lines...)
and until now the only observable output was the final ranking, which made
weight tuning guesswork. These tests pin the contract: the breakdown a profile
reports must *sum to the score it actually ranked with*, and the CLI must print
it.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from photopicker.classifier import StubClassifier
from photopicker.cli import main
from photopicker.profiles import RuleBreakdown, get_profile
from photopicker.profiles.aries import (
    AMBIENT_LIGHTS_LABEL,
    GREENERY_LABEL,
    GREENERY_WEIGHT,
    STAGE_LABELS,
    WARMTH_LABEL,
    WARMTH_WEIGHT,
    _combined,
)
from photopicker.profiles.big7 import CATEGORY_LABELS as BIG7_CATEGORY_LABELS
from photopicker.profiles.big7 import (
    CLEAN_LINES_LABEL,
    HERO_EXTERIOR_LABEL,
    PEOPLE_LABEL,
    PEOPLE_WEIGHT,
)


def _photo_folder(root: Path, count: int = 4) -> Path:
    """Uniform checker images — same quality for every photo, so the only thing
    moving the score is the rule contributions we're asserting on."""
    folder = root / "photos"
    folder.mkdir()
    arr = np.full((256, 256, 3), 128, dtype=np.uint8)
    for i in range(0, 256, 16):
        for j in range(0, 256, 16):
            if (i // 16 + j // 16) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    for i in range(count):
        Image.fromarray(arr).save(folder / f"img_{i:02d}.png")
    return folder


@pytest.fixture
def photos(tmp_path: Path) -> Path:
    return _photo_folder(tmp_path)


def test_rule_breakdown_total_is_quality_plus_contributions():
    breakdown = RuleBreakdown(quality=0.6, contributions={"warmth": 0.3, "greenery": 0.1})
    assert breakdown.total == pytest.approx(1.0)


def test_rule_breakdown_with_no_rules_totals_to_quality():
    assert RuleBreakdown(quality=0.42).total == pytest.approx(0.42)


def test_aries_explains_every_photo_it_scored(photos: Path):
    paths = sorted(photos.iterdir())
    sel = get_profile("aries").select(paths, StubClassifier())

    assert set(sel.explain) == set(paths), "every scored photo gets a breakdown"
    for breakdown in sel.explain.values():
        assert set(breakdown.contributions) == {"warmth", "greenery", "ambient-lights"}


def test_aries_breakdown_matches_the_score_it_ranked_with(photos: Path):
    """The printed table must equal the number the profile actually sorted on."""
    paths = sorted(photos.iterdir())
    scores = {
        paths[0].name: {
            STAGE_LABELS["after"]: 0.9,
            WARMTH_LABEL: 0.8,
            GREENERY_LABEL: 0.4,
            AMBIENT_LIGHTS_LABEL: 0.2,
        }
    }
    sel = get_profile("aries").select(paths, StubClassifier(scores=scores))

    breakdown = sel.explain[paths[0]]
    expected = _combined(breakdown.quality, warmth=0.8, greenery=0.4, ambient=0.2)
    assert breakdown.total == pytest.approx(expected)
    # And each rule's slice is weight x probability x quality — not a free-floating number.
    assert breakdown.contributions["warmth"] == pytest.approx(
        breakdown.quality * WARMTH_WEIGHT * 0.8
    )
    assert breakdown.contributions["greenery"] == pytest.approx(
        breakdown.quality * GREENERY_WEIGHT * 0.4
    )


def test_big7_breakdown_attributes_points_to_the_people_rule(photos: Path):
    paths = sorted(photos.iterdir())
    scores = {
        paths[0].name: {
            BIG7_CATEGORY_LABELS["build"]: 0.9,
            PEOPLE_LABEL: 1.0,
            CLEAN_LINES_LABEL: 0.0,
            HERO_EXTERIOR_LABEL: 0.0,
        }
    }
    sel = get_profile("big7").select(paths, StubClassifier(scores=scores))

    breakdown = sel.explain[paths[0]]
    assert breakdown.contributions["people"] == pytest.approx(
        breakdown.quality * PEOPLE_WEIGHT
    )
    assert breakdown.contributions["clean-lines"] == pytest.approx(0.0)
    # Rules that fired at zero stay in the table so users see what was considered.
    assert "hero-exterior" in breakdown.contributions


def test_benchmark_flag_prints_per_rule_contributions(photos: Path):
    result = CliRunner().invoke(
        main, ["--folder", str(photos), "--profile", "aries", "--dry-run", "--benchmark"]
    )

    assert result.exit_code == 0, result.output
    assert "== benchmark: score contributions ==" in result.output
    assert "quality" in result.output
    for rule in ("warmth", "greenery", "ambient-lights"):
        assert f"+ {rule}" in result.output
    assert "total" in result.output


def test_benchmark_flag_is_off_by_default(photos: Path):
    result = CliRunner().invoke(main, ["--folder", str(photos), "--profile", "aries", "--dry-run"])

    assert result.exit_code == 0, result.output
    # Match the header, not the bare word — pytest's tmp_path is named after the test.
    assert "== benchmark" not in result.output


def test_benchmark_says_so_when_profile_reports_no_breakdown(photos: Path):
    result = CliRunner().invoke(
        main, ["--folder", str(photos), "--profile", "default", "--dry-run", "--benchmark"]
    )

    assert result.exit_code == 0, result.output
    assert "does not report per-rule contributions" in result.output


def test_benchmark_json_out_carries_breakdown_for_picked_photos_only(photos: Path):
    result = CliRunner().invoke(
        main,
        ["--folder", str(photos), "--profile", "big7", "--dry-run", "--benchmark", "--json-out"],
    )

    assert result.exit_code == 0, result.output
    # --dry-run prints a "CLIP skipped" banner ahead of the JSON body.
    payload = json.loads(result.output[result.output.index("{") :])
    picked = {p for paths in payload["selection"].values() for p in paths}
    assert payload["benchmark"], "benchmark block should be populated"
    assert set(payload["benchmark"]) == picked

    entry = next(iter(payload["benchmark"].values()))
    assert entry["total"] == pytest.approx(
        entry["quality"] + sum(entry["contributions"].values())
    )
