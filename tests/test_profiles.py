from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image

from photopicker.classifier import StubClassifier
from photopicker.profiles import aries_gallery as aries_gallery_module
from photopicker.profiles import get_profile, list_profiles
from photopicker.profiles.aries import STAGE_LABELS, WARMTH_LABEL, WARMTH_WEIGHT, _combined


def _uniform_checker_folder(root: Path, count: int = 10) -> Path:
    """Every image is the same checker so quality is uniform across the folder.
    Lets warmth/stage tests isolate the classifier's ranking effect without the
    intrinsic quality gap that mixed fixtures introduce."""
    folder = root / "uniform_photos"
    folder.mkdir()
    arr = np.full((256, 256, 3), 128, dtype=np.uint8)
    for i in range(0, 256, 16):
        for j in range(0, 256, 16):
            if (i // 16 + j // 16) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    for i in range(count):
        Image.fromarray(arr).save(folder / f"img_{i:02d}.png")
    return folder


def _stage_probs(winner: str, confidence: float = 0.8) -> dict[str, float]:
    remainder = (1.0 - confidence) / 2
    return {
        label: confidence if stage == winner else remainder
        for stage, label in STAGE_LABELS.items()
    }


def test_builtin_profiles_registered():
    profiles = list_profiles()
    assert "aries" in profiles
    assert "aries-gallery" in profiles
    assert "default" in profiles
    assert "big7" in profiles


def test_aries_gallery_splits_by_phase_and_caps(folder_of_large_images: Path):
    # Use the larger fixture — the aries-gallery profile applies a min-resolution
    # quality gate that rejects the small folder_of_images fixture.
    paths = sorted(folder_of_large_images.iterdir())
    scores = {}
    # Alternate the 10 fixture images between phases so all 3 buckets fill up
    for i, p in enumerate(paths):
        stage = ("before", "during", "after")[i % 3]
        scores[p.name] = _stage_probs(stage)
    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries-gallery").select(paths, classifier)

    total = sum(len(v) for v in sel.categorized.values())
    assert total > 0
    assert set(sel.categorized.keys()) == {"before", "during", "after"}
    # cap enforced (default 8 per phase)
    for stage in ("before", "during", "after"):
        assert len(sel.categorized[stage]) <= 8


def test_aries_gallery_sorts_each_phase_chronologically(
    folder_of_distinct_large_images: Path, monkeypatch
):
    paths = sorted(folder_of_distinct_large_images.iterdir())
    # Force every survivor into the "before" bucket so we have a single non-trivial phase.
    scores = {p.name: _stage_probs("before") for p in paths}
    classifier = StubClassifier(scores=scores)

    # Reverse-chronological EXIF: newest file has the OLDEST timestamp, so
    # chronological sort must invert filename order.
    times = {p: datetime(2026, 1, 1 + i) for i, p in enumerate(reversed(paths))}
    monkeypatch.setattr(aries_gallery_module, "get_capture_time", lambda p: times.get(p))

    sel = get_profile("aries-gallery").select(paths, classifier)
    before = sel.categorized["before"]
    assert len(before) > 1
    stamped = [times[p] for p in before]
    assert stamped == sorted(stamped), "each phase should be oldest-first by capture time"


def test_aries_gallery_undated_photos_sort_after_dated(
    folder_of_distinct_large_images: Path, monkeypatch
):
    paths = sorted(folder_of_distinct_large_images.iterdir())
    scores = {p.name: _stage_probs("before") for p in paths}
    classifier = StubClassifier(scores=scores)

    # First half has EXIF, second half returns None.
    dated_paths = paths[: len(paths) // 2]
    dated = {p: datetime(2026, 1, 1 + i) for i, p in enumerate(dated_paths)}
    monkeypatch.setattr(aries_gallery_module, "get_capture_time", lambda p: dated.get(p))

    sel = get_profile("aries-gallery").select(paths, classifier)
    before = sel.categorized["before"]
    # All dated photos should appear before all undated ones.
    dated_positions = [i for i, p in enumerate(before) if p in dated]
    undated_positions = [i for i, p in enumerate(before) if p not in dated]
    if dated_positions and undated_positions:
        assert max(dated_positions) < min(undated_positions)


def test_aries_gallery_reports_rejects(folder_of_distinct_large_images: Path):
    paths = sorted(folder_of_distinct_large_images.iterdir())
    scores = {p.name: _stage_probs("before") for p in paths}
    sel = get_profile("aries-gallery").select(paths, StubClassifier(scores=scores))
    # rejected map always has the four canonical buckets, even when empty.
    assert set(sel.rejected.keys()) == {"duplicates", "unreadable", "too_small", "blurry"}


def test_selection_reject_counts_hides_empty_buckets():
    from photopicker.profiles.registry import Selection

    sel = Selection(
        categorized={"a": []},
        rejected={"duplicates": [Path("x.jpg")], "blurry": []},
    )
    counts = sel.reject_counts()
    assert counts == {"duplicates": 1}


def test_summary_includes_reject_block():
    from photopicker.core import PhotoPick
    from photopicker.profiles.registry import Selection

    pick = PhotoPick(
        profile="aries-gallery",
        selection=Selection(
            categorized={"before": [Path("a.jpg")]},
            rejected={"duplicates": [Path("x.jpg"), Path("y.jpg")]},
        ),
        source_folder=Path("/tmp/photos"),
    )
    out = pick.summary()
    assert "== rejected ==" in out
    assert "duplicates: 2" in out


def test_summary_omits_reject_block_when_none():
    from photopicker.core import PhotoPick
    from photopicker.profiles.registry import Selection

    pick = PhotoPick(
        profile="default",
        selection=Selection(categorized={"featured": [Path("a.jpg")]}),
        source_folder=Path("/tmp/photos"),
    )
    assert "== rejected ==" not in pick.summary()


def test_aries_picks_one_per_stage(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    scores = {paths[0].name: _stage_probs("before"),
              paths[1].name: _stage_probs("during"),
              paths[2].name: _stage_probs("after")}
    for p in paths[3:]:
        scores[p.name] = _stage_probs("before", confidence=0.4)

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    assert len(sel.categorized["before"]) == 1
    assert len(sel.categorized["during"]) == 1
    assert len(sel.categorized["after"]) == 1
    assert sel.categorized["before"][0] == paths[0]
    assert sel.categorized["during"][0] == paths[1]
    assert sel.categorized["after"][0] == paths[2]


def test_aries_others_cap_at_six(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    sel = get_profile("aries").select(paths, StubClassifier())
    assert len(sel.categorized["others"]) <= 6


def test_aries_no_duplicate_picks(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    sel = get_profile("aries").select(paths, StubClassifier())
    picked = sel.all_picked()
    assert len(picked) == len(set(picked))


def test_aries_uses_classifier_with_correct_labels(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    classifier = StubClassifier()
    get_profile("aries").select(paths, classifier)
    assert len(classifier.calls) == len(paths)
    expected = set(STAGE_LABELS.values()) | {WARMTH_LABEL}
    for _, labels in classifier.calls:
        assert set(labels) == expected


def test_aries_combined_helper_bounds_warmth_bonus():
    # Zero warmth -> quality passes through
    assert _combined(quality=1.0, warmth=0.0) == 1.0
    # Full warmth -> quality boosted by WARMTH_WEIGHT
    assert _combined(quality=1.0, warmth=1.0) == 1.0 + WARMTH_WEIGHT
    # Boost is proportional
    assert _combined(quality=2.0, warmth=0.5) == 2.0 * (1.0 + 0.5 * WARMTH_WEIGHT)


def test_aries_warmth_breaks_tie_within_stage(tmp_path: Path):
    """Two photos with equal stage prob -> the warmer one wins.

    Uses a uniform-quality fixture so warmth is the only differentiator; the
    default `folder_of_images` mixes checker + gradient patterns which puts an
    intrinsic quality gap between adjacent paths.
    """
    folder = _uniform_checker_folder(tmp_path, count=10)
    paths = sorted(folder.iterdir())
    scores = {}
    scores[paths[0].name] = {**_stage_probs("after"), WARMTH_LABEL: 0.05}
    scores[paths[1].name] = {**_stage_probs("after"), WARMTH_LABEL: 0.95}
    for p in paths[2:]:
        scores[p.name] = {**_stage_probs("before", confidence=0.4), WARMTH_LABEL: 0.0}

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    assert sel.categorized["after"][0] == paths[1], (
        "warmer photo should win when stage probability is tied"
    )


def test_aries_warmth_boosts_others_ranking(tmp_path: Path):
    """Warmth influences the 'others' fallback ranking, not just stage picks."""
    folder = _uniform_checker_folder(tmp_path, count=10)
    paths = sorted(folder.iterdir())
    warmth_ranked = paths[3:9]
    scores = {}
    scores[paths[0].name] = {**_stage_probs("before"), WARMTH_LABEL: 0.0}
    scores[paths[1].name] = {**_stage_probs("during"), WARMTH_LABEL: 0.0}
    scores[paths[2].name] = {**_stage_probs("after"), WARMTH_LABEL: 0.0}
    for i, p in enumerate(warmth_ranked):
        scores[p.name] = {
            **_stage_probs("before", confidence=0.4),
            WARMTH_LABEL: 1.0 - (i * 0.1),
        }
    for p in paths[9:]:
        scores[p.name] = {**_stage_probs("before", confidence=0.4), WARMTH_LABEL: 0.0}

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    others = sel.categorized["others"]
    assert warmth_ranked[0] in others
    assert others.index(warmth_ranked[0]) < others.index(warmth_ranked[-1])


def test_default_profile_returns_top_n(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    sel = get_profile("default").select(paths, StubClassifier())
    assert "featured" in sel.categorized
    assert len(sel.categorized["featured"]) == 9


def test_default_profile_sorted_by_quality(folder_of_images: Path):
    from photopicker.scoring import composite_score

    paths = sorted(folder_of_images.iterdir())
    sel = get_profile("default").select(paths, StubClassifier())
    featured = sel.categorized["featured"]
    scores = [composite_score(p) for p in featured]
    assert scores == sorted(scores, reverse=True)


def test_big7_splits_into_repair_and_build(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    sel = get_profile("big7").select(paths, StubClassifier())
    assert "repair" in sel.categorized
    assert "build" in sel.categorized
    assert len(sel.categorized["repair"]) <= 6
    assert len(sel.categorized["build"]) <= 6


def test_get_profile_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        get_profile("nonexistent")
