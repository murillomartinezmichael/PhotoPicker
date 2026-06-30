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
