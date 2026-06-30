from __future__ import annotations

from pathlib import Path

from photopicker.classifier import StubClassifier
from photopicker.profiles import get_profile, list_profiles
from photopicker.profiles.aries import STAGE_LABELS


def _stage_probs(winner: str, confidence: float = 0.8) -> dict[str, float]:
    remainder = (1.0 - confidence) / 2
    return {
        label: confidence if stage == winner else remainder
        for stage, label in STAGE_LABELS.items()
    }


def test_builtin_profiles_registered():
    profiles = list_profiles()
    assert "aries" in profiles
    assert "default" in profiles
    assert "big7" in profiles


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
    for _, labels in classifier.calls:
        assert set(labels) == set(STAGE_LABELS.values())


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
