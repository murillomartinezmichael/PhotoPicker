from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image

_SHARPNESS_CAP = 1000.0


def sharpness_score(path: Path) -> float:
    img = _load_grayscale(path)
    if img is None:
        return 0.0
    return float(cv2.Laplacian(img, cv2.CV_64F).var())


def exposure_score(path: Path) -> float:
    img = _load_grayscale(path)
    if img is None:
        return 0.0
    mean = float(img.mean()) / 255.0
    return float(1.0 - abs(mean - 0.5) * 2.0)


def composite_score(path: Path) -> float:
    sharp_norm = min(sharpness_score(path) / _SHARPNESS_CAP, 1.0)
    return 0.7 * sharp_norm + 0.3 * exposure_score(path)


def _load_grayscale(path: Path) -> np.ndarray | None:
    try:
        with Image.open(path) as img:
            gray = img.convert("L")
            gray.thumbnail((1024, 1024))
            return np.asarray(gray)
    except Exception:
        return None
