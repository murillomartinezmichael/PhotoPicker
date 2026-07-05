"""RUNG 1 HARDEN tests for convert.py — corrupt / unreadable images.

The web UI /photo endpoint and the Vision rerank loop both call
`thumbnail_bytes` and `vision_bytes` on user-supplied files. A single corrupt
file must not crash either surface — it should raise `ImageUnreadable` which
callers translate into "skip this one" or a real 500 with a message.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from photopicker.convert import ImageUnreadable, thumbnail_bytes, vision_bytes


def _write_junk(path: Path, size: int = 128) -> None:
    path.write_bytes(b"\x00" * 8 + b"junk_not_an_image_" + b"\xff" * (size - 26))


def test_thumbnail_bytes_raises_image_unreadable_on_junk(tmp_path: Path):
    bad = tmp_path / "not_a_photo.jpg"
    _write_junk(bad)

    with pytest.raises(ImageUnreadable) as exc_info:
        thumbnail_bytes(bad, width=200)
    assert "not_a_photo.jpg" in str(exc_info.value)


def test_thumbnail_bytes_raises_on_missing_file(tmp_path: Path):
    missing = tmp_path / "does_not_exist.png"

    with pytest.raises(ImageUnreadable):
        thumbnail_bytes(missing, width=200)


def test_vision_bytes_raises_image_unreadable_on_junk(tmp_path: Path):
    bad = tmp_path / "corrupt.png"
    _write_junk(bad)

    with pytest.raises(ImageUnreadable):
        vision_bytes(bad)


def test_vision_bytes_raises_image_unreadable_on_zero_byte(tmp_path: Path):
    empty = tmp_path / "empty.jpg"
    empty.write_bytes(b"")

    with pytest.raises(ImageUnreadable):
        vision_bytes(empty)


def test_vision_bytes_bad_fmt_still_raises_value_error_not_unreadable(tmp_path: Path):
    """API contract: ValueError for bad format arg to thumbnail_bytes stays a
    ValueError — that's a caller bug, not a source-file issue."""
    good = tmp_path / "good.png"
    from PIL import Image
    Image.new("RGB", (100, 100)).save(good)

    with pytest.raises(ValueError, match="Unknown fmt"):
        thumbnail_bytes(good, width=50, fmt="tiff")
