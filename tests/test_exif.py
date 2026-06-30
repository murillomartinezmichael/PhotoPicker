from __future__ import annotations

from datetime import datetime
from pathlib import Path

from photopicker.exif import _parse_exif_datetime, get_capture_time


def test_parse_standard_format():
    assert _parse_exif_datetime("2026:04:15 14:30:00") == datetime(2026, 4, 15, 14, 30, 0)


def test_parse_dash_format():
    assert _parse_exif_datetime("2026-04-15 14:30:00") == datetime(2026, 4, 15, 14, 30, 0)


def test_parse_invalid_returns_none():
    assert _parse_exif_datetime("not a date") is None
    assert _parse_exif_datetime(None) is None
    assert _parse_exif_datetime(12345) is None


def test_image_without_exif_returns_none(sharp_image: Path):
    assert get_capture_time(sharp_image) is None


def test_missing_file_returns_none(tmp_path: Path):
    assert get_capture_time(tmp_path / "nonexistent.png") is None
