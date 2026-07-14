from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from photopicker.dedup import (
    average_hash,
    collapse_heic_jpg_twins,
    dedup_all,
    dedup_perceptual,
    hamming_distance,
)


def _write_solid(path: Path, value: int, size: tuple[int, int] = (256, 256)) -> Path:
    arr = np.full((size[1], size[0], 3), value, dtype=np.uint8)
    Image.fromarray(arr).save(path)
    return path


def _write_gradient(path: Path, seed: int = 0, size: tuple[int, int] = (256, 256)) -> Path:
    arr = np.zeros((size[1], size[0], 3), dtype=np.uint8)
    for i in range(size[1]):
        arr[i, :] = (i + seed) % 256
    Image.fromarray(arr).save(path)
    return path


def test_average_hash_is_stable(tmp_path):
    a = _write_gradient(tmp_path / "a.png", seed=0)
    b = _write_gradient(tmp_path / "b.png", seed=0)
    assert average_hash(a) == average_hash(b)


def test_average_hash_differs_for_different_content(tmp_path):
    a = _write_gradient(tmp_path / "a.png", seed=0)
    b = _write_solid(tmp_path / "b.png", value=200)
    assert hamming_distance(average_hash(a), average_hash(b)) > 6


def test_dedup_perceptual_collapses_identical_content(tmp_path):
    paths = [
        _write_gradient(tmp_path / "a.png", seed=0),
        _write_gradient(tmp_path / "b.png", seed=0),
        _write_gradient(tmp_path / "c.png", seed=0),
        _write_solid(tmp_path / "d.png", value=200),
    ]
    kept = dedup_perceptual(paths)
    # Only 2 unique images: one gradient cluster + one solid
    assert len(kept) == 2


def test_dedup_perceptual_respects_threshold(tmp_path):
    # Two visually different images — gradient vs solid have a large hash distance,
    # so threshold=0 keeps both, threshold=64 (max) collapses them.
    a = _write_gradient(tmp_path / "a.png", seed=0)
    b = _write_solid(tmp_path / "b.png", value=200)
    assert len(dedup_perceptual([a, b], threshold=0)) == 2
    assert len(dedup_perceptual([a, b], threshold=64)) == 1


def test_collapse_heic_jpg_twins_prefers_jpg(tmp_path):
    # Simulate iOS-style stems (HEIC + JPG twin with same date+time+iOS suffix)
    heic = _write_gradient(tmp_path / "20250515_165138438_iOS.heic", seed=0)
    jpg = _write_gradient(tmp_path / "20250515_165138438_iOS.jpg", seed=0)
    solo = _write_gradient(tmp_path / "20250516_120000123_iOS.jpg", seed=10)

    kept = collapse_heic_jpg_twins([heic, jpg, solo])
    names = {p.name for p in kept}
    assert "20250515_165138438_iOS.jpg" in names  # JPG wins over HEIC twin
    assert "20250515_165138438_iOS.heic" not in names
    assert "20250516_120000123_iOS.jpg" in names  # solo passes through
    assert len(kept) == 2


def test_collapse_heic_jpg_twins_passes_non_ios_names(tmp_path):
    a = _write_gradient(tmp_path / "arbitrary_name.jpg", seed=0)
    b = _write_gradient(tmp_path / "another_file.jpg", seed=1)
    kept = collapse_heic_jpg_twins([a, b])
    assert len(kept) == 2


def test_dedup_perceptual_passes_through_unhashable(tmp_path):
    # A corrupt file can't be hashed. It must survive dedup so the quality gate
    # is the one that rejects it (reason "unreadable") — dropping it here made it
    # look like a duplicate.
    good = _write_gradient(tmp_path / "good.png", seed=0)
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"not an image")

    kept = dedup_perceptual([good, corrupt])
    assert kept == [good, corrupt]


def test_dedup_all_passes_through_unhashable(tmp_path):
    corrupt = tmp_path / "corrupt.jpg"
    corrupt.write_bytes(b"\xff\xd8truncated")
    assert dedup_all([corrupt]) == [corrupt]


def test_dedup_all_combines_twin_and_perceptual(tmp_path):
    # Two twin pairs (identical content in each pair)
    _write_gradient(tmp_path / "20250515_100000001_iOS.heic", seed=0)
    p1 = _write_gradient(tmp_path / "20250515_100000001_iOS.jpg", seed=0)
    _write_gradient(tmp_path / "20250516_100000001_iOS.heic", seed=0)
    p2 = _write_gradient(tmp_path / "20250516_100000001_iOS.jpg", seed=0)

    # After twin dedup: 2 JPGs remain. Both identical content -> perceptual collapses to 1.
    kept = dedup_all([p1, p2, p1.parent / "20250515_100000001_iOS.heic",
                      p1.parent / "20250516_100000001_iOS.heic"])
    assert len(kept) == 1
