from __future__ import annotations

from pathlib import Path
from typing import Protocol

from PIL import Image


class Classifier(Protocol):
    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        ...


class ClipClassifier:
    """Production classifier — lazy-loads CLIP on first call.

    Requires the `clip` extra (`pip install photopicker[clip]`).
    """

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32") -> None:
        self._model_name = model_name
        self._model = None
        self._processor = None

    def _load(self) -> None:
        if self._model is not None:
            return
        from transformers import CLIPModel, CLIPProcessor

        self._model = CLIPModel.from_pretrained(self._model_name)
        self._processor = CLIPProcessor.from_pretrained(self._model_name)

    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        import torch

        self._load()
        assert self._model is not None and self._processor is not None
        with Image.open(image_path) as img:
            rgb = img.convert("RGB")
            inputs = self._processor(
                text=labels, images=rgb, return_tensors="pt", padding=True
            )
            with torch.no_grad():
                outputs = self._model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)[0].tolist()
        return dict(zip(labels, probs, strict=True))


class StubClassifier:
    """Test/offline classifier. Returns canned scores by filename, else uniform."""

    def __init__(self, scores: dict[str, dict[str, float]] | None = None) -> None:
        self.scores = scores or {}
        self.calls: list[tuple[Path, list[str]]] = []

    def score(self, image_path: Path, labels: list[str]) -> dict[str, float]:
        self.calls.append((image_path, labels))
        canned = self.scores.get(image_path.name)
        if canned is not None:
            return {label: canned.get(label, 0.0) for label in labels}
        return {label: 1.0 / len(labels) for label in labels}
