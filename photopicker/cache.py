"""Disk-persisted score cache — wrap any Classifier to skip CLIP re-runs.

Tuning galleries (per-phase cap, threshold tweaks, profile A/B) means running
the pipeline over the same folder five times in a row. CLIP is by far the
slowest step; caching its output makes iteration nearly free.

Cache key: (absolute path, mtime, size, sorted labels tuple). Any change to the
file or the label set forces a re-score, so callers cannot see stale results.
"""
from __future__ import annotations

import json
from pathlib import Path

from .classifier import Classifier, classify_batch


class CachingClassifier:
    def __init__(self, inner: Classifier, cache_path: Path | str) -> None:
        self.inner = inner
        self.cache_path = Path(cache_path)
        self._cache: dict[str, dict[str, float]] = self._load()

    def _load(self) -> dict[str, dict[str, float]]:
        if not self.cache_path.exists():
            return {}
        try:
            with self.cache_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        except (json.JSONDecodeError, OSError):
            return {}

    def _flush(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with self.cache_path.open("w", encoding="utf-8") as fh:
            json.dump(self._cache, fh, indent=2, sort_keys=True)

    @staticmethod
    def _key(image_path: Path, labels: list[str]) -> str:
        st = image_path.stat()
        label_sig = "|".join(sorted(labels))
        return f"{image_path.resolve()}::{st.st_mtime_ns}::{st.st_size}::{label_sig}"

    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        key = self._key(image_path, labels)
        cached = self._cache.get(key)
        if cached is not None and set(cached.keys()) == set(labels):
            return dict(cached)
        fresh = self.inner.score(image_path, labels)
        self._cache[key] = dict(fresh)
        self._flush()
        return fresh

    def score_batch(
        self, image_paths: list[Path], labels: list[str]
    ) -> dict[Path, dict[str, float]]:
        results: dict[Path, dict[str, float]] = {}
        misses: list[Path] = []
        for p in image_paths:
            key = self._key(p, labels)
            cached = self._cache.get(key)
            if cached is not None and set(cached.keys()) == set(labels):
                results[p] = dict(cached)
            else:
                misses.append(p)
        if misses:
            fresh = classify_batch(self.inner, misses, labels)
            for p, probs in fresh.items():
                key = self._key(p, labels)
                self._cache[key] = dict(probs)
                results[p] = probs
            self._flush()
        return results

    def stats(self) -> dict[str, int]:
        return {"entries": len(self._cache)}
