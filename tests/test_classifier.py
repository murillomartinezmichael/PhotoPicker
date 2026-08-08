from __future__ import annotations

import sys
from pathlib import Path

import pytest

from photopicker.classifier import ClipClassifier, StubClassifier


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


def test_clip_missing_torch_names_the_extra(sharp_image: Path, monkeypatch):
    """Without the [clip] extra, score_batch must say how to install it — not
    leak a bare ModuleNotFoundError. None in sys.modules forces the ImportError
    even on machines that do have torch."""
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(ImportError, match=r"photopicker\[clip\]"):
        ClipClassifier().score_batch([sharp_image], ["a"])


def test_clip_missing_transformers_names_the_extra(monkeypatch):
    monkeypatch.setitem(sys.modules, "transformers", None)
    with pytest.raises(ImportError, match=r"photopicker\[clip\]"):
        ClipClassifier()._load()
