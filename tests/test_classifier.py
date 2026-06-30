from __future__ import annotations

from pathlib import Path

from photopicker.classifier import StubClassifier


def test_stub_returns_canned_scores(sharp_image: Path):
    stub = StubClassifier(scores={sharp_image.name: {"a": 0.9, "b": 0.1}})
    result = stub.score(sharp_image, ["a", "b"])
    assert result == {"a": 0.9, "b": 0.1}


def test_stub_uniform_fallback(sharp_image: Path):
    stub = StubClassifier()
    result = stub.score(sharp_image, ["x", "y", "z"])
    assert all(abs(v - 1 / 3) < 1e-9 for v in result.values())


def test_stub_records_calls(sharp_image: Path, blurry_image: Path):
    stub = StubClassifier()
    stub.score(sharp_image, ["a"])
    stub.score(blurry_image, ["b"])
    assert len(stub.calls) == 2
    assert stub.calls[0][0] == sharp_image


def test_stub_extracts_only_requested_labels(sharp_image: Path):
    stub = StubClassifier(scores={sharp_image.name: {"a": 0.5, "b": 0.5}})
    result = stub.score(sharp_image, ["a"])
    assert result == {"a": 0.5}
