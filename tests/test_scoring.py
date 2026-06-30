from __future__ import annotations

from pathlib import Path

from photopicker.scoring import composite_score, exposure_score, sharpness_score


def test_sharp_image_scores_higher_than_blurry(sharp_image: Path, blurry_image: Path):
    assert sharpness_score(sharp_image) > sharpness_score(blurry_image)


def test_midtone_exposure_better_than_dark(midtone_image: Path, dark_image: Path):
    assert exposure_score(midtone_image) > exposure_score(dark_image)


def test_midtone_exposure_better_than_bright(midtone_image: Path, bright_image: Path):
    assert exposure_score(midtone_image) > exposure_score(bright_image)


def test_composite_in_range(sharp_image: Path):
    score = composite_score(sharp_image)
    assert 0.0 <= score <= 1.0


def test_dark_composite_below_midtone(midtone_image: Path, dark_image: Path):
    assert composite_score(midtone_image) > composite_score(dark_image)


def test_missing_file_returns_zero(tmp_path: Path):
    missing = tmp_path / "nope.png"
    assert sharpness_score(missing) == 0.0
    assert exposure_score(missing) == 0.0
    assert composite_score(missing) == 0.0
