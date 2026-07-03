from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image


def _checker(shape=(256, 256, 3)) -> Image.Image:
    arr = np.full(shape, 128, dtype=np.uint8)
    for i in range(0, shape[0], 16):
        for j in range(0, shape[1], 16):
            if (i // 16 + j // 16) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    return Image.fromarray(arr)


def _gradient(shape=(256, 256, 3)) -> Image.Image:
    arr = np.zeros(shape, dtype=np.uint8)
    for i in range(shape[0]):
        arr[i, :] = i % 256
    return Image.fromarray(arr)


def _solid(shape=(256, 256, 3), value: int = 128) -> Image.Image:
    arr = np.full(shape, value, dtype=np.uint8)
    return Image.fromarray(arr)


@pytest.fixture
def sharp_image(tmp_path: Path) -> Path:
    p = tmp_path / "sharp.png"
    _checker().save(p)
    return p


@pytest.fixture
def blurry_image(tmp_path: Path) -> Path:
    p = tmp_path / "blurry.png"
    _gradient().save(p)
    return p


@pytest.fixture
def dark_image(tmp_path: Path) -> Path:
    p = tmp_path / "dark.png"
    _solid(value=10).save(p)
    return p


@pytest.fixture
def bright_image(tmp_path: Path) -> Path:
    p = tmp_path / "bright.png"
    _solid(value=245).save(p)
    return p


@pytest.fixture
def midtone_image(tmp_path: Path) -> Path:
    p = tmp_path / "midtone.png"
    _checker().save(p)
    return p


@pytest.fixture
def folder_of_images(tmp_path: Path) -> Path:
    folder = tmp_path / "photos"
    folder.mkdir()
    for i in range(10):
        img = _checker() if i % 2 == 0 else _gradient()
        img.save(folder / f"img_{i:02d}.png")
    return folder


@pytest.fixture
def folder_of_large_images(tmp_path: Path) -> Path:
    """Larger images that pass the quality gate's default min_long_edge (800)."""
    folder = tmp_path / "large_photos"
    folder.mkdir()
    shape = (900, 900, 3)
    for i in range(10):
        img = _checker(shape=shape) if i % 2 == 0 else _checker(shape=shape)
        img.save(folder / f"img_{i:02d}.png")
    return folder


@pytest.fixture
def folder_of_distinct_large_images(tmp_path: Path) -> Path:
    """10 visually distinct large images — pass both quality gate and perceptual dedup."""
    folder = tmp_path / "distinct_photos"
    folder.mkdir()
    shape = (900, 900, 3)
    for i in range(10):
        arr = np.full(shape, 128, dtype=np.uint8)
        # Unique per-image pattern: different quadrant is bright.
        row_off = (i * 90) % shape[0]
        col_off = (i * 71) % shape[1]
        arr[row_off : row_off + 200, col_off : col_off + 200] = 255
        # Add checker so quality gate accepts (sharpness > 60).
        for r in range(0, shape[0], 32):
            for c in range(0, shape[1], 32):
                if (r // 32 + c // 32) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = min(255, 200 + i * 5)
        Image.fromarray(arr).save(folder / f"img_{i:02d}.png")
    return folder
