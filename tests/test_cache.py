from __future__ import annotations

import json
import os
import time
from pathlib import Path

from photopicker.cache import CachingClassifier
from photopicker.classifier import StubClassifier


def _touch_newer(path: Path) -> None:
    st = path.stat()
    # Bump mtime by 2s so mtime_ns changes even on filesystems with coarse resolution.
    new_time = st.st_mtime + 2
    os.utime(path, (new_time, new_time))


def test_cache_miss_calls_inner(sharp_image: Path, tmp_path: Path):
    inner = StubClassifier(scores={sharp_image.name: {"cat": 0.9, "dog": 0.1}})
    cache = CachingClassifier(inner, tmp_path / "c.json")

    result = cache.score(sharp_image, ["cat", "dog"])
    assert result == {"cat": 0.9, "dog": 0.1}
    assert len(inner.calls) == 1


def test_cache_hit_skips_inner(sharp_image: Path, tmp_path: Path):
    inner = StubClassifier(scores={sharp_image.name: {"cat": 0.9, "dog": 0.1}})
    cache = CachingClassifier(inner, tmp_path / "c.json")

    cache.score(sharp_image, ["cat", "dog"])
    cache.score(sharp_image, ["cat", "dog"])
    cache.score(sharp_image, ["cat", "dog"])
    assert len(inner.calls) == 1


def test_cache_persists_across_instances(sharp_image: Path, tmp_path: Path):
    cache_file = tmp_path / "c.json"
    inner_a = StubClassifier(scores={sharp_image.name: {"cat": 0.9, "dog": 0.1}})
    CachingClassifier(inner_a, cache_file).score(sharp_image, ["cat", "dog"])

    # Fresh classifier, fresh cache instance, same file → hit.
    inner_b = StubClassifier(scores={sharp_image.name: {"cat": 0.9, "dog": 0.1}})
    cache_b = CachingClassifier(inner_b, cache_file)
    cache_b.score(sharp_image, ["cat", "dog"])
    assert len(inner_b.calls) == 0


def test_mtime_change_invalidates(sharp_image: Path, tmp_path: Path):
    inner = StubClassifier(scores={sharp_image.name: {"cat": 0.9, "dog": 0.1}})
    cache = CachingClassifier(inner, tmp_path / "c.json")
    cache.score(sharp_image, ["cat", "dog"])

    # Give filesystem a beat, then bump mtime.
    time.sleep(0.01)
    _touch_newer(sharp_image)

    cache.score(sharp_image, ["cat", "dog"])
    assert len(inner.calls) == 2, "mtime change should invalidate cache"


def test_different_labels_do_not_collide(sharp_image: Path, tmp_path: Path):
    inner = StubClassifier(
        scores={sharp_image.name: {"a": 0.5, "b": 0.3, "c": 0.2, "d": 0.9}}
    )
    cache = CachingClassifier(inner, tmp_path / "c.json")
    cache.score(sharp_image, ["a", "b", "c"])
    cache.score(sharp_image, ["a", "d"])
    # Two different label sets → two different keys → two inner calls.
    assert len(inner.calls) == 2


def test_label_order_normalized(sharp_image: Path, tmp_path: Path):
    inner = StubClassifier(scores={sharp_image.name: {"a": 0.5, "b": 0.5}})
    cache = CachingClassifier(inner, tmp_path / "c.json")
    cache.score(sharp_image, ["a", "b"])
    cache.score(sharp_image, ["b", "a"])
    # Same labels in different order → same cache key.
    assert len(inner.calls) == 1


def test_corrupt_cache_file_recovers(sharp_image: Path, tmp_path: Path):
    cache_file = tmp_path / "c.json"
    cache_file.write_text("{ not json")

    inner = StubClassifier(scores={sharp_image.name: {"cat": 0.9, "dog": 0.1}})
    cache = CachingClassifier(inner, cache_file)
    result = cache.score(sharp_image, ["cat", "dog"])
    assert result == {"cat": 0.9, "dog": 0.1}
    # Corrupt file was replaced with a valid one.
    with cache_file.open() as fh:
        json.load(fh)


def test_stats_reports_entries(sharp_image: Path, tmp_path: Path):
    inner = StubClassifier(scores={sharp_image.name: {"a": 1.0}})
    cache = CachingClassifier(inner, tmp_path / "c.json")
    assert cache.stats() == {"entries": 0}
    cache.score(sharp_image, ["a"])
    assert cache.stats() == {"entries": 1}
