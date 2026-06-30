from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL import ExifTags, Image

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass


_DATETIME_TAGS = ("DateTimeOriginal", "DateTime", "DateTimeDigitized")
_TAG_TO_ID = {name: tid for tid, name in ExifTags.TAGS.items()}


def get_capture_time(path: Path) -> datetime | None:
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            if not exif:
                return None
            for tag_name in _DATETIME_TAGS:
                tid = _TAG_TO_ID.get(tag_name)
                if tid and tid in exif:
                    parsed = _parse_exif_datetime(exif[tid])
                    if parsed is not None:
                        return parsed
    except Exception:
        return None
    return None


def _parse_exif_datetime(raw: object) -> datetime | None:
    if not isinstance(raw, str):
        return None
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None
