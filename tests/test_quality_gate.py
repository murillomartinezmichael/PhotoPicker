from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from photopicker.quality_gate import check, filter_usable


def _write_solid(path: Path, value: int, size: tuple[int, int] = (900, 900)) -> Path:
    arr = np.full((size[1], size[0], 3), value, dtype=np.uint8)
    Image.fromarray(arr).save(path)
    return path


def _write_checker(path: Path, size: tuple[int, int] = (900, 900)) -> Path:
    arr = np.full((size[1], size[0], 3), 128, dtype=np.uint8)
    for i in range(0, size[1], 16):
        for j in range(0, size[0], 16):
            if (i // 16 + j // 16) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    Image.fromarray(arr).save(path)
    return path


def test_check_accepts_a_sharp_image(sharp_image):
    # conftest sharp_image is 256x256 — bump min_long_edge down so we're only testing sharpness
    r = check(sharp_image, min_long_edge=200)
    assert r.kept is True
    assert r.sharpness > 60


def test_check_rejects_a_flat_image_as_blurry(tmp_path):
    p = _write_solid(tmp_path / "flat.png", value=128)
    r = check(p)
    assert r.kept is False
    assert "blurry" in r.reason


def test_check_rejects_tiny_image(tmp_path):
    tiny = _write_checker(tmp_path / "tiny.png", size=(200, 200))
    r = check(tiny)
    assert r.kept is False
    assert "too small" in r.reason


def test_check_rejects_unreadable(tmp_path):
    bad = tmp_path / "not-an-image.png"
    bad.write_text("this is not a png")
    r = check(bad)
    assert r.kept is False
    assert r.reason == "unreadable"


def test_filter_usable_returns_kept_paths_and_full_results(tmp_path):
    good = _write_checker(tmp_path / "good.png")
    flat = _write_solid(tmp_path / "flat.png", value=128)
    tiny = _write_checker(tmp_path / "tiny.png", size=(200, 200))

    kept, results = filter_usable([good, flat, tiny])
    assert kept == [good]
    assert len(results) == 3
    assert {r.path for r in results if not r.kept} == {flat, tiny}
