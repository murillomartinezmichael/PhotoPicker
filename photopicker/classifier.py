from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

from PIL import Image

DEFAULT_BATCH_SIZE = 32

# Mirrors vision.py's missing-extra message so every optional dep fails the same way.
CLIP_INSTALL_HINT = (
    "CLIP semantic labels need `pip install photopicker[clip]`. "
    "Install it, or pass --dry-run (StubClassifier in code) to skip CLIP."
)


class Classifier(Protocol):
    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        ...


def classify_batch(
    classifier: Classifier,
    paths: Sequence[Path],
    labels: list[str],
) -> dict[Path, dict[str, float]]:
    """Run a classifier over many images, using its native batch path if available.

    Classifiers can implement `score_batch(paths, labels) -> dict[Path, dict]`
    for real speed-ups (one CLIP forward pass over N images). Anything without
    that method transparently falls back to per-image `score()`.
    """
    batch_fn = getattr(classifier, "score_batch", None)
    if batch_fn is not None:
        return batch_fn(list(paths), labels)
    return {p: classifier.score(p, labels) for p in paths}


class ClipClassifier:
    """Production classifier — lazy-loads CLIP on first call.

    Requires the `clip` extra (`pip install photopicker[clip]`).
    """

    def __init__(
        self,
        model_name: str = "openai/clip-vit-base-patch32",
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:
        self._model_name = model_name
        self._model = None
        self._processor = None
        self.batch_size = batch_size

    def _load(self) -> None:
        if self._model is not None:
            return
        try:
            from transformers import CLIPModel, CLIPProcessor
        except ImportError as exc:
            raise ImportError(CLIP_INSTALL_HINT) from exc

        self._model = CLIPModel.from_pretrained(self._model_name)
        self._processor = CLIPProcessor.from_pretrained(self._model_name)

    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        result = self.score_batch([image_path], labels)
        return result[image_path]

    def score_batch(
        self, image_paths: list[Path], labels: list[str]
    ) -> dict[Path, dict[str, float]]:
        try:
            import torch
        except ImportError as exc:
            raise ImportError(CLIP_INSTALL_HINT) from exc

        self._load()
        assert self._model is not None and self._processor is not None

        results: dict[Path, dict[str, float]] = {}
        # Chunk so a 500-photo folder doesn't blow GPU/CPU memory.
        for start in range(0, len(image_paths), self.batch_size):
            chunk = image_paths[start : start + self.batch_size]
            images = []
            for p in chunk:
                with Image.open(p) as img:
                    images.append(img.convert("RGB").copy())
            inputs = self._processor(
                text=labels, images=images, return_tensors="pt", padding=True
            )
            with torch.no_grad():
                outputs = self._model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1).tolist()
            for path, row in zip(chunk, probs, strict=True):
                results[path] = dict(zip(labels, row, strict=True))
        return results


class StubClassifier:
    """Test/offline classifier. Returns canned scores by filename, else uniform."""

    def __init__(self, scores: dict[str, dict[str, float]] | None = None) -> None:
        self.scores = scores or {}
        self.calls: list[tuple[Path, list[str]]] = []
        self.batch_calls: list[tuple[list[Path], list[str]]] = []

    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        self.calls.append((image_path, labels))
        canned = self.scores.get(image_path.name)
        if canned is not None:
            return {label: canned.get(label, 0.0) for label in labels}
        return {label: 1.0 / len(labels) for label in labels}

    def score_batch(
        self, image_paths: list[Path], labels: list[str]
    ) -> dict[Path, dict[str, float]]:
        self.batch_calls.append((list(image_paths), labels))
        return {p: self.score(p, labels) for p in image_paths}
