from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photopicker.classifier import StubClassifier
from photopicker.profiles import aries_gallery as aries_gallery_module
from photopicker.profiles import get_profile, list_profiles
from photopicker.profiles.aries import (
    AMBIENT_LIGHTS_LABEL,
    AMBIENT_LIGHTS_WEIGHT,
    FURNISHED_LABEL,
    FURNISHED_WEIGHT,
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
    CLEAN_LINES_WEIGHT,
    FINISHED_RESULT_LABEL,
    FINISHED_RESULT_WEIGHT,
    HERO_EXTERIOR_LABEL,
    HERO_EXTERIOR_WEIGHT,
    PEOPLE_LABEL,
    PEOPLE_WEIGHT,
)
from photopicker.profiles.big7 import _combined as _big7_combined


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
    expected = set(STAGE_LABELS.values()) | {
        WARMTH_LABEL,
        GREENERY_LABEL,
        AMBIENT_LIGHTS_LABEL,
        FURNISHED_LABEL,
    }
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


def test_aries_combined_stacks_greenery_bonus_additively():
    # Greenery alone applies its own weight.
    assert _combined(quality=1.0, warmth=0.0, greenery=1.0) == 1.0 + GREENERY_WEIGHT
    # Warmth + greenery stack additively inside the multiplier.
    expected = 1.0 * (1.0 + WARMTH_WEIGHT + GREENERY_WEIGHT)
    assert _combined(quality=1.0, warmth=1.0, greenery=1.0) == expected
    # Greenery defaults to 0 so pre-existing callers stay warmth-only (back-compat).
    assert _combined(quality=1.0, warmth=0.4) == _combined(
        quality=1.0, warmth=0.4, greenery=0.0
    )


def test_aries_greenery_bonus_ranks_planted_deck_above_bare(tmp_path: Path):
    """Two 'after' shots, equal quality + equal warmth -> the greenery one wins.

    Uses uniform-quality fixtures so greenery is the only differentiator.
    """
    folder = _uniform_checker_folder(tmp_path, count=10)
    paths = sorted(folder.iterdir())
    scores = {}
    scores[paths[0].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.0,
    }
    scores[paths[1].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.95,
    }
    for p in paths[2:]:
        scores[p.name] = {
            **_stage_probs("before", confidence=0.4),
            WARMTH_LABEL: 0.0,
            GREENERY_LABEL: 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    assert sel.categorized["after"][0] == paths[1], (
        "shot with lush landscaping should outrank equal-quality bare shot"
    )


def test_aries_warmth_dominates_greenery(tmp_path: Path):
    """When warmth and greenery fire on different shots, warmth wins.

    Locks the design intent: golden-hour is the primary aesthetic signal,
    greenery is a secondary bonus. If someone rebalances the weights and
    inverts this ordering, the test fails loudly.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    scores = {}
    # paths[0]: warmth only
    # paths[1]: greenery only
    # everyone else: neither
    scores[paths[0].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.9,
        GREENERY_LABEL: 0.0,
    }
    scores[paths[1].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.9,
    }
    for p in paths[2:]:
        scores[p.name] = {
            **_stage_probs("before", confidence=0.4),
            WARMTH_LABEL: 0.0,
            GREENERY_LABEL: 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    # Only one photo lands in the "after" slot (aries picks 1/stage), so the
    # warmth-only shot should claim it and the greenery shot flows to "others".
    assert sel.categorized["after"][0] == paths[0], (
        "warmth-only shot should outrank a greenery-only shot within the same stage"
    )
    assert paths[1] in sel.categorized["others"]


def test_aries_combined_stacks_ambient_bonus_additively():
    # Ambient alone applies its own weight.
    assert _combined(quality=1.0, warmth=0.0, greenery=0.0, ambient=1.0) == (
        1.0 + AMBIENT_LIGHTS_WEIGHT
    )
    # All three bonuses stack additively inside the multiplier.
    expected = 1.0 * (1.0 + WARMTH_WEIGHT + GREENERY_WEIGHT + AMBIENT_LIGHTS_WEIGHT)
    assert _combined(quality=1.0, warmth=1.0, greenery=1.0, ambient=1.0) == pytest.approx(
        expected
    )
    # Ambient defaults to 0 for callers that don't pass it (back-compat).
    assert _combined(quality=1.0, warmth=0.4, greenery=0.2) == _combined(
        quality=1.0, warmth=0.4, greenery=0.2, ambient=0.0
    )


def test_aries_ambient_bonus_ranks_lit_evening_scene_above_bare(tmp_path: Path):
    """Two 'after' shots, equal quality + no warmth + no greenery -> the string-lit one wins.

    Uses uniform-quality fixtures so ambient lighting is the only differentiator.
    """
    folder = _uniform_checker_folder(tmp_path, count=10)
    paths = sorted(folder.iterdir())
    scores = {}
    scores[paths[0].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.0,
        AMBIENT_LIGHTS_LABEL: 0.0,
    }
    scores[paths[1].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.0,
        AMBIENT_LIGHTS_LABEL: 0.95,
    }
    for p in paths[2:]:
        scores[p.name] = {
            **_stage_probs("before", confidence=0.4),
            WARMTH_LABEL: 0.0,
            GREENERY_LABEL: 0.0,
            AMBIENT_LIGHTS_LABEL: 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    assert sel.categorized["after"][0] == paths[1], (
        "string-lit evening shot should outrank equal-quality bare shot"
    )


def test_aries_greenery_dominates_ambient(tmp_path: Path):
    """Greenery (0.2) outranks ambient (0.15) when they fire on different shots.

    Locks the weight ordering: WARMTH > GREENERY > AMBIENT. If someone flips
    ambient above greenery, this test fails loudly.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    scores = {}
    # paths[0]: greenery only
    # paths[1]: ambient only
    # others: neither
    scores[paths[0].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.9,
        AMBIENT_LIGHTS_LABEL: 0.0,
    }
    scores[paths[1].name] = {
        **_stage_probs("after"),
        WARMTH_LABEL: 0.0,
        GREENERY_LABEL: 0.0,
        AMBIENT_LIGHTS_LABEL: 0.9,
    }
    for p in paths[2:]:
        scores[p.name] = {
            **_stage_probs("before", confidence=0.4),
            WARMTH_LABEL: 0.0,
            GREENERY_LABEL: 0.0,
            AMBIENT_LIGHTS_LABEL: 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    # Only one photo lands in the "after" slot, so greenery shot claims it and
    # the ambient shot flows to "others".
    assert sel.categorized["after"][0] == paths[0], (
        "greenery-only shot should outrank an ambient-only shot within the same stage"
    )
    assert paths[1] in sel.categorized["others"]


def test_aries_combined_stacks_furnished_bonus_additively():
    # Furnished alone applies its own weight.
    assert _combined(quality=1.0, warmth=0.0, furnished=1.0) == 1.0 + FURNISHED_WEIGHT
    # All four bonuses stack additively inside the multiplier.
    expected = 1.0 * (
        1.0 + WARMTH_WEIGHT + GREENERY_WEIGHT + AMBIENT_LIGHTS_WEIGHT + FURNISHED_WEIGHT
    )
    assert _combined(
        quality=1.0, warmth=1.0, greenery=1.0, ambient=1.0, furnished=1.0
    ) == pytest.approx(expected)
    # Furnished defaults to 0 for callers that don't pass it (back-compat).
    assert _combined(quality=1.0, warmth=0.4, ambient=0.2) == _combined(
        quality=1.0, warmth=0.4, ambient=0.2, furnished=0.0
    )


def test_aries_furnished_bonus_ranks_staged_deck_above_empty(tmp_path: Path):
    """Two 'after' shots, identical on every other rule -> the staged one wins.

    Uniform-quality fixtures, so outdoor furniture is the only differentiator.
    """
    folder = _uniform_checker_folder(tmp_path, count=10)
    paths = sorted(folder.iterdir())
    scores = {}
    scores[paths[0].name] = {**_stage_probs("after"), FURNISHED_LABEL: 0.0}
    scores[paths[1].name] = {**_stage_probs("after"), FURNISHED_LABEL: 0.95}
    for p in paths[2:]:
        scores[p.name] = {**_stage_probs("before", confidence=0.4), FURNISHED_LABEL: 0.0}

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    assert sel.categorized["after"][0] == paths[1], (
        "deck staged with furniture should outrank an equal-quality empty deck"
    )


def test_aries_ambient_dominates_furnished(tmp_path: Path):
    """Ambient (0.15) outranks furnished (0.12) when they fire on different shots.

    Locks the full weight ordering: WARMTH > GREENERY > AMBIENT > FURNISHED.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    scores = {}
    # paths[0]: ambient only, paths[1]: furnished only, others: neither.
    scores[paths[0].name] = {
        **_stage_probs("after"),
        AMBIENT_LIGHTS_LABEL: 0.9,
        FURNISHED_LABEL: 0.0,
    }
    scores[paths[1].name] = {
        **_stage_probs("after"),
        AMBIENT_LIGHTS_LABEL: 0.0,
        FURNISHED_LABEL: 0.9,
    }
    for p in paths[2:]:
        scores[p.name] = {
            **_stage_probs("before", confidence=0.4),
            AMBIENT_LIGHTS_LABEL: 0.0,
            FURNISHED_LABEL: 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("aries").select(paths, classifier)

    # Aries picks one photo per stage, so the ambient shot claims "after" and the
    # furnished shot flows to "others".
    assert sel.categorized["after"][0] == paths[0], (
        "ambient-only shot should outrank a furnished-only shot within the same stage"
    )
    assert paths[1] in sel.categorized["others"]


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


def test_big7_combined_scales_quality_by_people_bonus():
    # Baseline quality unchanged when no people detected.
    assert _big7_combined(quality=1.0, people=0.0) == 1.0
    # Full people prob applies the full PEOPLE_WEIGHT boost.
    assert _big7_combined(quality=1.0, people=1.0) == 1.0 + PEOPLE_WEIGHT
    # Boost is proportional to quality * people.
    assert _big7_combined(quality=2.0, people=0.5) == 2.0 * (1.0 + 0.5 * PEOPLE_WEIGHT)


def test_big7_combined_stacks_clean_lines_bonus_additively():
    # Clean-lines alone applies its own weight.
    assert _big7_combined(quality=1.0, people=0.0, clean_lines=1.0) == 1.0 + CLEAN_LINES_WEIGHT
    # People + clean-lines stack additively inside the multiplier.
    expected = 1.0 * (1.0 + PEOPLE_WEIGHT + CLEAN_LINES_WEIGHT)
    assert _big7_combined(quality=1.0, people=1.0, clean_lines=1.0) == expected
    # Clean-lines defaults to 0 for callers that don't pass it (back-compat).
    assert _big7_combined(quality=1.0, people=0.4) == _big7_combined(
        quality=1.0, people=0.4, clean_lines=0.0
    )


def test_big7_people_bonus_ranks_workers_shot_above_empty_wall(tmp_path: Path):
    """Within the same bucket, a photo with visible crew wins over an equal-quality empty shot.

    Uses uniform-quality fixtures so the people bonus is the only differentiator.
    """
    folder = _uniform_checker_folder(tmp_path, count=6)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    # All 6 land in the "repair" bucket. paths[1] has crew in frame; others don't.
    scores = {}
    for i, p in enumerate(paths):
        scores[p.name] = {
            repair_label: 0.9,
            build_label: 0.1,
            PEOPLE_LABEL: 0.95 if i == 1 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["repair"][0] == paths[1], (
        "shot with crew + tools should outrank equal-quality empty shot"
    )


def test_big7_clean_lines_bonus_ranks_symmetric_shot_above_cluttered(tmp_path: Path):
    """Within the same bucket and equal quality, a clean-lines shot outranks a cluttered one.

    Uses uniform-quality fixtures so clean-lines is the only differentiator.
    """
    folder = _uniform_checker_folder(tmp_path, count=6)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    # All 6 land in "build"; paths[3] reads as clean/square-framed, others don't.
    # No people in any shot so the people bonus is zeroed out.
    scores = {}
    for i, p in enumerate(paths):
        scores[p.name] = {
            repair_label: 0.1,
            build_label: 0.9,
            PEOPLE_LABEL: 0.0,
            CLEAN_LINES_LABEL: 0.9 if i == 3 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["build"][0] == paths[3], (
        "clean-lines shot should outrank cluttered equal-quality shots"
    )


def test_big7_people_bonus_dominates_clean_lines(tmp_path: Path):
    """People bonus outweighs clean lines when both fire on different shots.

    Locks the design intent: crew-on-site is the primary signal, clean-lines
    is a tiebreaker. If someone rebalances the weights and inverts this,
    the test fails loudly.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    scores = {}
    for i, p in enumerate(paths):
        # paths[0]: crew on site, no clean lines
        # paths[1]: clean lines, no crew
        # everyone else: neither
        scores[p.name] = {
            repair_label: 0.9,
            build_label: 0.1,
            PEOPLE_LABEL: 0.9 if i == 0 else 0.0,
            CLEAN_LINES_LABEL: 0.9 if i == 1 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["repair"][0] == paths[0], (
        "crew-on-site shot should still outrank a clean-lines-only shot"
    )
    assert sel.categorized["repair"][1] == paths[1], (
        "clean-lines shot should place second, ahead of shots with neither signal"
    )


def test_big7_combined_stacks_finished_result_bonus_additively():
    # Finished alone applies its own weight.
    assert _big7_combined(quality=1.0, people=0.0, clean_lines=0.0, finished=1.0) == (
        1.0 + FINISHED_RESULT_WEIGHT
    )
    # All three bonuses stack additively inside the multiplier.
    expected = 1.0 * (1.0 + PEOPLE_WEIGHT + CLEAN_LINES_WEIGHT + FINISHED_RESULT_WEIGHT)
    assert _big7_combined(
        quality=1.0, people=1.0, clean_lines=1.0, finished=1.0
    ) == pytest.approx(expected)
    # Finished defaults to 0 for callers that don't pass it (back-compat).
    assert _big7_combined(quality=1.0, people=0.4, clean_lines=0.2) == _big7_combined(
        quality=1.0, people=0.4, clean_lines=0.2, finished=0.0
    )


def test_big7_combined_stacks_hero_exterior_bonus_additively():
    # Hero alone applies its own weight.
    assert _big7_combined(
        quality=1.0, people=0.0, clean_lines=0.0, finished=0.0, hero=1.0
    ) == (1.0 + HERO_EXTERIOR_WEIGHT)
    # All four bonuses stack additively inside the multiplier.
    expected = 1.0 * (
        1.0 + PEOPLE_WEIGHT + CLEAN_LINES_WEIGHT + FINISHED_RESULT_WEIGHT + HERO_EXTERIOR_WEIGHT
    )
    assert (
        _big7_combined(quality=1.0, people=1.0, clean_lines=1.0, finished=1.0, hero=1.0)
        == expected
    )
    # Hero defaults to 0 for callers that don't pass it (back-compat).
    assert _big7_combined(
        quality=1.0, people=0.4, clean_lines=0.2, finished=0.1
    ) == _big7_combined(quality=1.0, people=0.4, clean_lines=0.2, finished=0.1, hero=0.0)


def test_big7_hero_exterior_bonus_ranks_above_baseline(tmp_path: Path):
    """Between equal-quality shots with no other signal, the one reading as a
    hero-exterior curb-appeal frame outranks the baseline shots.

    Locks the design intent that hero-exterior is a real signal — the
    residential-GC money shot is worth a small bump on its own.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    # All 4 land in "build"; paths[2] reads as hero-exterior, others don't.
    # No people, no clean-lines, no finished — hero is the only differentiator.
    scores = {}
    for i, p in enumerate(paths):
        scores[p.name] = {
            repair_label: 0.1,
            build_label: 0.9,
            PEOPLE_LABEL: 0.0,
            CLEAN_LINES_LABEL: 0.0,
            FINISHED_RESULT_LABEL: 0.0,
            HERO_EXTERIOR_LABEL: 0.9 if i == 2 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["build"][0] == paths[2], (
        "hero-exterior shot should outrank equal-quality shots with no signal"
    )


def test_big7_finished_result_dominates_hero_exterior(tmp_path: Path):
    """Finished-result outranks hero-exterior when they fire on different shots.

    Locks the weight ordering: FINISHED_RESULT (0.15) > HERO_EXTERIOR (0.1).
    If someone flips the weights, this fails loudly.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    scores = {}
    for i, p in enumerate(paths):
        # paths[0]: finished, not hero
        # paths[1]: hero, not finished
        # others: neither
        scores[p.name] = {
            repair_label: 0.1,
            build_label: 0.9,
            PEOPLE_LABEL: 0.0,
            CLEAN_LINES_LABEL: 0.0,
            FINISHED_RESULT_LABEL: 0.9 if i == 0 else 0.0,
            HERO_EXTERIOR_LABEL: 0.9 if i == 1 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["build"][0] == paths[0], (
        "finished-result shot should outrank a hero-exterior-only shot"
    )
    assert sel.categorized["build"][1] == paths[1], (
        "hero-exterior shot should place second, ahead of shots with neither signal"
    )


def test_big7_finished_result_bonus_ranks_completed_above_debris(tmp_path: Path):
    """Between two equal-quality shots with no crew and no clean-lines signal,
    the one reading as 'finished' outranks the mid-repair shot.

    Locks the design intent that finished-result is a real signal, small but
    non-zero — sales/marketing shots skew toward completed work.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    # All 4 land in "build"; paths[2] reads as finished, others don't.
    # No people and no clean-lines in any shot so finished is the only differentiator.
    scores = {}
    for i, p in enumerate(paths):
        scores[p.name] = {
            repair_label: 0.1,
            build_label: 0.9,
            PEOPLE_LABEL: 0.0,
            CLEAN_LINES_LABEL: 0.0,
            FINISHED_RESULT_LABEL: 0.9 if i == 2 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["build"][0] == paths[2], (
        "finished-result shot should outrank equal-quality mid-repair shots"
    )


def test_big7_clean_lines_dominates_finished_result(tmp_path: Path):
    """Clean-lines outranks finished-result when they fire on different shots.

    Locks the weight ordering: CLEAN_LINES (0.3) > FINISHED_RESULT (0.15).
    If someone flips the weights, this fails loudly.
    """
    folder = _uniform_checker_folder(tmp_path, count=4)
    paths = sorted(folder.iterdir())
    repair_label = BIG7_CATEGORY_LABELS["repair"]
    build_label = BIG7_CATEGORY_LABELS["build"]

    scores = {}
    for i, p in enumerate(paths):
        # paths[0]: clean lines, not finished
        # paths[1]: finished, not clean lines
        # others: neither
        scores[p.name] = {
            repair_label: 0.1,
            build_label: 0.9,
            PEOPLE_LABEL: 0.0,
            CLEAN_LINES_LABEL: 0.9 if i == 0 else 0.0,
            FINISHED_RESULT_LABEL: 0.9 if i == 1 else 0.0,
        }

    classifier = StubClassifier(scores=scores)
    sel = get_profile("big7").select(paths, classifier)

    assert sel.categorized["build"][0] == paths[0], (
        "clean-lines shot should outrank a finished-only shot"
    )
    assert sel.categorized["build"][1] == paths[1], (
        "finished-result shot should place second, ahead of shots with neither signal"
    )


def test_get_profile_unknown_raises():
    import pytest

    with pytest.raises(KeyError):
        get_profile("nonexistent")
