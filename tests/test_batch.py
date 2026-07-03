"""Batch classification path — new in 0.5.0."""
from __future__ import annotations

from pathlib import Path

from photopicker.cache import CachingClassifier
from photopicker.classifier import (
    Classifier,
    StubClassifier,
    classify_batch,
)


class _PerImageOnly:
    """Classifier without score_batch — tests the classify_batch fallback."""

    def __init__(self) -> None:
        self.calls: list[Path] = []

    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        self.calls.append(image_path)
        return {label: 1.0 / len(labels) for label in labels}


def test_classify_batch_uses_score_batch_when_available(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    stub = StubClassifier()

    out = classify_batch(stub, paths, ["a", "b"])

    assert set(out.keys()) == set(paths)
    assert len(stub.batch_calls) == 1
    assert stub.batch_calls[0][0] == paths


def test_classify_batch_falls_back_to_per_image(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    inner = _PerImageOnly()

    out = classify_batch(inner, paths, ["a", "b"])

    assert set(out.keys()) == set(paths)
    assert inner.calls == list(paths)


def test_classify_batch_matches_per_image_results(sharp_image: Path):
    scores = {sharp_image.name: {"cat": 0.9, "dog": 0.1}}
    stub = StubClassifier(scores=scores)

    single = stub.score(sharp_image, ["cat", "dog"])
    batched = classify_batch(stub, [sharp_image], ["cat", "dog"])

    assert batched[sharp_image] == single


def test_stub_batch_call_records_full_path_list(folder_of_images: Path):
    paths = sorted(folder_of_images.iterdir())
    stub = StubClassifier()

    classify_batch(stub, paths[:3], ["x", "y"])
    classify_batch(stub, paths[3:5], ["x", "y"])

    assert len(stub.batch_calls) == 2
    assert stub.batch_calls[0][0] == paths[:3]
    assert stub.batch_calls[1][0] == paths[3:5]


def test_caching_classifier_batch_serves_hits_and_dispatches_misses(
    folder_of_images: Path, tmp_path: Path
):
    paths = sorted(folder_of_images.iterdir())
    inner = StubClassifier(scores={p.name: {"a": 0.5, "b": 0.5} for p in paths})
    cache = CachingClassifier(inner, tmp_path / "c.json")

    # First batch: all misses.
    first = cache.score_batch(paths[:5], ["a", "b"])
    assert len(first) == 5
    # StubClassifier.score_batch recorded one dispatch for all 5.
    assert len(inner.batch_calls) == 1
    assert inner.batch_calls[0][0] == paths[:5]

    # Second batch: 3 overlap with cache + 2 new.
    second = cache.score_batch(paths[2:7], ["a", "b"])
    assert len(second) == 5
    # Inner only sees the two misses (paths[5], paths[6]).
    assert len(inner.batch_calls) == 2
    assert inner.batch_calls[1][0] == paths[5:7]


def test_caching_classifier_batch_persists_across_instances(
    folder_of_images: Path, tmp_path: Path
):
    paths = sorted(folder_of_images.iterdir())
    cache_file = tmp_path / "c.json"

    inner_a = StubClassifier(scores={p.name: {"a": 0.5, "b": 0.5} for p in paths})
    CachingClassifier(inner_a, cache_file).score_batch(paths[:3], ["a", "b"])
    assert len(inner_a.batch_calls) == 1

    # Fresh instance loads the same cache file → no re-dispatch.
    inner_b = StubClassifier(scores={p.name: {"a": 0.5, "b": 0.5} for p in paths})
    result = CachingClassifier(inner_b, cache_file).score_batch(paths[:3], ["a", "b"])
    assert len(result) == 3
    assert inner_b.batch_calls == []


def test_profile_selections_identical_batch_vs_per_image(folder_of_images: Path):
    """Same profile, same photos, one classifier with batch and one without —
    must produce identical selections."""
    from photopicker.profiles import get_profile

    paths = sorted(folder_of_images.iterdir())

    stub = StubClassifier()
    per_image: Classifier = _PerImageOnly()

    batched_sel = get_profile("big7").select(paths, stub)
    perimg_sel = get_profile("big7").select(paths, per_image)

    assert batched_sel.categorized == perimg_sel.categorized
