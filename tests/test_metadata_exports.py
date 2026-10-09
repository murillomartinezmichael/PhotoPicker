"""Real HEIF and ordinary camera EXIF survive the public export paths."""
from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from photopicker.convert import copy_or_transcode, generate_thumbnails, to_webp, transcode_to_jpg
from photopicker.exif import get_capture_time

CAPTURE = "2026:10:03 09:15:00"
EXPECTED = datetime(2026, 10, 3, 9, 15)


@pytest.fixture(params=["JPEG", "HEIF"])
def camera_image(tmp_path, request):
    if request.param == "HEIF":
        # Real x265/libheif encoding of a synthetic blue rectangle. No encoder
        # or private camera photo is needed to run the decoder regression.
        source = Path(__file__).parent / "fixtures" / "synthetic-metadata.heic"
        path = tmp_path / source.name
        path.write_bytes(source.read_bytes())
    else:
        path = tmp_path / "camera.jpg"
        exif = Image.Exif()
        exif[271] = "Synthetic camera"
        exif[0x8769] = {36867: CAPTURE}
        Image.new("RGB", (960, 640), (40, 140, 210)).save(path, "JPEG", exif=exif)
    with Image.open(path) as image:
        assert image.format == request.param
        assert image.getexif().get_ifd(0x8769)[36867] == CAPTURE
    return path


def test_nested_capture_time_is_read_from_camera_image(camera_image):
    assert get_capture_time(camera_image) == EXPECTED


def test_actual_heic_publish_path_retains_capture_time(tmp_path):
    source = Path(__file__).parent / "fixtures" / "synthetic-metadata.heic"
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = copy_or_transcode(source, tmp_path, target_name="before-01.jpg")
    with Image.open(output) as image:
        assert image.format == "JPEG"
        assert image.size == (960, 640)
    assert get_capture_time(output) == EXPECTED
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("kind", ["jpeg", "webp", "jpeg-thumb", "webp-thumb"])
def test_saved_exports_preserve_capture_metadata_and_source(camera_image, tmp_path, kind):
    before = hashlib.sha256(camera_image.read_bytes()).hexdigest()
    if kind == "jpeg":
        output = transcode_to_jpg(camera_image, tmp_path / "export.jpg")
    elif kind == "webp":
        output = to_webp(camera_image, tmp_path / "export.webp")
    else:
        fmt = "jpg" if kind == "jpeg-thumb" else "webp"
        output = generate_thumbnails(camera_image, tmp_path / "thumbs", "export", [320], fmt=fmt)[320]
    with Image.open(output) as image:
        image.load()
        assert image.size == ((320, 213) if "thumb" in kind else (960, 640))
        assert image.getexif().get_ifd(0x8769).get(36867) == CAPTURE
        assert image.getexif().get(271) == "Synthetic camera"
    assert get_capture_time(output) == EXPECTED
    assert hashlib.sha256(camera_image.read_bytes()).hexdigest() == before


@pytest.mark.parametrize("original, expected", [(CAPTURE, EXPECTED), ("invalid", datetime(2025, 1, 2, 3, 4, 5))])
def test_capture_time_prefers_nested_original_then_valid_fallback(tmp_path, original, expected):
    path = tmp_path / "fallback.jpg"
    exif = Image.Exif()
    exif[306] = "2025:01:02 03:04:05"
    exif[0x8769] = {36867: original}
    Image.new("RGB", (40, 30)).save(path, "JPEG", exif=exif)
    assert get_capture_time(path) == expected
