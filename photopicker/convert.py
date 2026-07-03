"""HEIC → JPG transcoding + anonymized naming for browser-safe output.

iPhone galleries are HEIC. Web browsers can't render HEIC. The publish flow —
`photopicker --folder ~/photos --profile aries-gallery --output ~/site/img`
should produce a folder your static site can serve directly. That means any
HEIC that came in must leave as JPG.

Non-HEIC files (JPG, PNG, WEBP) are copied byte-for-byte via `shutil.copy2` to
preserve EXIF and mtime.

Rename schemes let published files anonymize their source (`IMG_4231.jpg` →
`before-01.jpg`), important for client-facing galleries where original iPhone
filenames leak zero useful info and can leak private context.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PIL import Image

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:
    pass

_HEIC_EXTS = {".heic", ".heif"}
DEFAULT_JPG_QUALITY = 92
DEFAULT_THUMBNAIL_QUALITY = 85
DEFAULT_WEBP_QUALITY = 82

RENAME_SCHEMES = ("original", "sequential", "category-rank")
_FORMAT_TO_EXT = {"jpg": ".jpg", "webp": ".webp"}
_FORMAT_TO_PIL = {"jpg": "JPEG", "webp": "WEBP"}


def generate_thumbnails(
    source: Path,
    dest_dir: Path,
    base_stem: str,
    widths: list[int],
    quality: int = DEFAULT_THUMBNAIL_QUALITY,
    fmt: str = "jpg",
) -> dict[int, Path]:
    """Emit a set of `<base_stem>-<width>w.<ext>` files scaled by width.

    Aspect ratio is preserved. Widths larger than the source width are skipped
    (no upscaling — nothing to gain, image only gets worse). `fmt` chooses
    between `"jpg"` (default) and `"webp"`. Returns a map of the widths
    actually produced → destination paths, ready to feed a `<picture>` srcset.
    """
    if not widths:
        return {}
    if fmt not in _FORMAT_TO_EXT:
        raise ValueError(f"Unknown fmt {fmt!r}. Choose from {sorted(_FORMAT_TO_EXT)}")
    ext = _FORMAT_TO_EXT[fmt]
    pil_fmt = _FORMAT_TO_PIL[fmt]
    save_kwargs: dict[str, object] = {"quality": quality}
    if pil_fmt == "JPEG":
        save_kwargs["optimize"] = True
    else:
        # method=6 = slowest/best WebP encoder setting; fine for offline publish.
        save_kwargs["method"] = 6

    dest_dir.mkdir(parents=True, exist_ok=True)
    produced: dict[int, Path] = {}
    with Image.open(source) as img:
        rgb = img.convert("RGB")
        original_w, original_h = rgb.size
        for width in sorted(set(widths)):
            if width >= original_w:
                continue
            new_h = round(original_h * (width / original_w))
            resized = rgb.resize((width, new_h), Image.LANCZOS)
            dest = dest_dir / f"{base_stem}-{width}w{ext}"
            resized.save(dest, pil_fmt, **save_kwargs)
            produced[width] = dest
    return produced


def resolve_output_name(
    source: Path,
    category: str,
    rank_in_category: int,
    global_rank: int,
    total_picks: int,
    scheme: str,
    convert_heic: bool = True,
) -> str:
    """Compute the target filename for a picked photo.

    `original` → keep source name.
    `sequential` → `01.jpg`, `02.jpg`, ... globally (zero-pad by total_picks).
    `category-rank` → `<category>-01.jpg`, `<category>-02.jpg`, ...

    Extension follows the transcoded file (JPG if HEIC + convert_heic, else the
    source extension), so downstream naming stays consistent with the actual
    file bytes.
    """
    is_heic = source.suffix.lower() in _HEIC_EXTS
    ext = ".jpg" if (convert_heic and is_heic) else source.suffix.lower()

    if scheme == "original":
        # If we transcoded, the source name still needs its extension swapped.
        if convert_heic and is_heic:
            return f"{source.stem}.jpg"
        return source.name

    pad = max(2, len(str(total_picks)))
    if scheme == "sequential":
        return f"{str(global_rank).zfill(pad)}{ext}"
    if scheme == "category-rank":
        return f"{category}-{str(rank_in_category).zfill(pad)}{ext}"
    raise ValueError(
        f"Unknown rename scheme {scheme!r}. Choose one of {RENAME_SCHEMES}."
    )


def transcode_to_jpg(source: Path, dest: Path, quality: int = DEFAULT_JPG_QUALITY) -> Path:
    """Read `source` (any Pillow-supported format) and write `dest` as JPEG."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        img.convert("RGB").save(dest, "JPEG", quality=quality, optimize=True)
    return dest


def to_webp(source: Path, dest: Path, quality: int = DEFAULT_WEBP_QUALITY) -> Path:
    """Read `source` (any Pillow-supported format) and write `dest` as WebP.

    WebP at quality 82 is roughly equivalent to JPEG at quality 92 by eye but
    typically 25-35% smaller. Ships alongside the JPG so browsers negotiate
    format via `<source type="image/webp">`.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as img:
        img.convert("RGB").save(dest, "WEBP", quality=quality, method=6)
    return dest


def copy_or_transcode(
    source: Path,
    dest_dir: Path,
    convert_heic: bool = True,
    quality: int = DEFAULT_JPG_QUALITY,
    target_name: str | None = None,
) -> Path:
    """Publish `source` into `dest_dir`.

    HEIC + `convert_heic=True` → transcode to `<stem>.jpg` (or `target_name`).
    Anything else → byte-for-byte copy preserving mtime/EXIF.
    When `target_name` is set it overrides the derived filename — used for
    anonymized/sequential rename schemes.
    Returns the resolved destination path.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    is_heic = source.suffix.lower() in _HEIC_EXTS
    if convert_heic and is_heic:
        dest = dest_dir / (target_name or f"{source.stem}.jpg")
        return transcode_to_jpg(source, dest, quality)
    dest = dest_dir / (target_name or source.name)
    shutil.copy2(source, dest)
    return dest
