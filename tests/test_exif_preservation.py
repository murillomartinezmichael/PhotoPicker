"""Verify originals are never modified and EXIF survives the export path.

Constraint from the finish line: cull must never touch the source, and any
export must preserve EXIF so downstream galleries can use capture time /
camera / GPS metadata.

Uses Pillow's built-in `Image.Exif` (no piexif dep needed) to inject a
DateTimeOriginal tag and read it back post-copy.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import numpy as np
from PIL import Image

from photopicker.convert import copy_or_transcode
from photopicker.culler import cull

_DATETIME_ORIGINAL = 36867  # PIL/EXIF tag id for DateTimeOriginal
_MAKE_TAG = 271
_MODEL_TAG = 272


def _make_with_exif(path: Path, capture: str = "2026:07:05 12:34:56") -> None:
    arr = np.full((900, 900, 3), 128, dtype=np.uint8)
    for r in range(0, 900, 16):
        for c in range(0, 900, 16):
            if (r // 16 + c // 16) % 2 == 0:
                arr[r : r + 16, c : c + 16] = 255
    img = Image.fromarray(arr)
    exif = img.getexif()
    exif[_MAKE_TAG] = "TestCam"
    exif[_MODEL_TAG] = "Model X"
    exif[_DATETIME_ORIGINAL] = capture
    img.save(path, "JPEG", quality=92, exif=exif.tobytes())


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_exif_datetime(path: Path) -> str | None:
    """Return the DateTimeOriginal string from a saved JPEG, or None if absent.

    Pillow-written EXIF can land the tag in the top-level 0th IFD or in the
    Exif sub-IFD depending on how it was assigned. Check both.
    """
    with Image.open(path) as img:
        exif = img.getexif()
        raw = exif.get(_DATETIME_ORIGINAL)
        if raw is None:
            try:
                sub = exif.get_ifd(0x8769)
                raw = sub.get(_DATETIME_ORIGINAL)
            except Exception:
                raw = None
    return raw


def test_originals_are_unchanged_after_cull(tmp_path: Path):
    folder = tmp_path / "shoot"
    folder.mkdir()
    for i in range(6):
        _make_with_exif(folder / f"IMG_{i:04d}.jpg", capture=f"2026:07:05 12:00:{i:02d}")
    hashes_before = {p.name: _sha256(p) for p in folder.iterdir()}

    result = cull(sorted(folder.iterdir()), top_n=3)
    assert len(result.keepers) > 0

    hashes_after = {p.name: _sha256(p) for p in folder.iterdir()}
    assert hashes_before == hashes_after, "source folder must not change during cull"


def test_copy_or_transcode_preserves_exif_for_jpg(tmp_path: Path):
    src = tmp_path / "IMG_0001.jpg"
    _make_with_exif(src, capture="2026:07:05 15:22:11")
    target = tmp_path / "out"

    dest = copy_or_transcode(src, target, convert_heic=False)

    assert dest.exists()
    got = _read_exif_datetime(dest)
    assert got == "2026:07:05 15:22:11"


def test_copy_or_transcode_byte_identical_for_jpg_source(tmp_path: Path):
    src = tmp_path / "IMG_0002.jpg"
    _make_with_exif(src)
    target = tmp_path / "out"

    dest = copy_or_transcode(src, target, convert_heic=False)

    # shutil.copy2 preserves bytes exactly for JPG passthrough.
    assert _sha256(src) == _sha256(dest)


def test_source_mtime_preserved_on_jpg_copy(tmp_path: Path):
    src = tmp_path / "IMG_0003.jpg"
    _make_with_exif(src)
    fixed_ts = 1_800_000_000
    os.utime(src, (fixed_ts, fixed_ts))
    target = tmp_path / "out"

    dest = copy_or_transcode(src, target, convert_heic=False)

    assert int(dest.stat().st_mtime) == fixed_ts
