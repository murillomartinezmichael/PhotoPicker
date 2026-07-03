"""Hard-reject filters for obviously unusable frames.

Scoring (in `scoring.py`) *ranks* photos; the quality gate *rejects* them.
Both cutoffs are tunable so profiles can be strict (portfolio hero shots) or
lenient (documentation frames).
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

# Sharpness = Laplacian variance on the greyscale image.
# Iphone photos in focus typically score >200 on 1024px thumbnails.
# Below 50 = obviously blurry (motion blur, out of focus).
DEFAULT_MIN_SHARPNESS = 60.0
DEFAULT_MIN_LONG_EDGE = 800  # skip thumbnails / broken exports


@dataclass
class GateResult:
    path: Path
    kept: bool
    reason: str = ""
    sharpness: float = 0.0
    long_edge: int = 0


def _load_grayscale_and_size(path: Path) -> tuple[np.ndarray | None, int]:
    try:
        with Image.open(path) as img:
            w, h = img.size
            gray = img.convert("L")
            gray.thumbnail((1024, 1024))
            return np.asarray(gray), max(w, h)
    except Exception:
        return None, 0


def check(
    path: Path,
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
    min_long_edge: int = DEFAULT_MIN_LONG_EDGE,
) -> GateResult:
    gray, long_edge = _load_grayscale_and_size(path)
    if gray is None:
        return GateResult(path=path, kept=False, reason="unreadable")
    if long_edge < min_long_edge:
        return GateResult(
            path=path, kept=False, reason=f"too small ({long_edge}px < {min_long_edge})",
            long_edge=long_edge,
        )
    sharp = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if sharp < min_sharpness:
        return GateResult(
            path=path, kept=False, reason=f"blurry (sharpness {sharp:.1f} < {min_sharpness})",
            sharpness=sharp, long_edge=long_edge,
        )
    return GateResult(path=path, kept=True, sharpness=sharp, long_edge=long_edge)


def filter_usable(
    paths: Iterable[Path],
    min_sharpness: float = DEFAULT_MIN_SHARPNESS,
    min_long_edge: int = DEFAULT_MIN_LONG_EDGE,
) -> tuple[list[Path], list[GateResult]]:
    """Return `(kept_paths, all_results)` — the results list has both kept and
    rejected entries so callers can log/report why a photo was cut."""
    results = [check(p, min_sharpness, min_long_edge) for p in paths]
    kept = [r.path for r in results if r.kept]
    return kept, results
