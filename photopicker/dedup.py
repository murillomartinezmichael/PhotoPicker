"""Duplicate rejection — HEIC/JPG twin collapse + perceptual hash near-dup.

Twin collapse: iOS exports the same shot as `<stem>_iOS.heic` AND `<stem>_iOS.jpg`
with identical timestamps. When both exist we keep the JPG (browser-native, no
decode dependency for downstream).

Perceptual dedup: 8x8 average-hash Hamming distance. `threshold=6` treats near-
duplicates (burst shots, slight framing changes) as the same photo. Bump to 4
for stricter, 10 for looser.
"""
from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from PIL import Image

_JPG_EXTS = {".jpg", ".jpeg"}
_HEIC_EXTS = {".heic", ".heif"}
_AHASH_SIZE = 8
DEFAULT_HAMMING_THRESHOLD = 6


def average_hash(path: Path, size: int = _AHASH_SIZE) -> int:
    """8x8 average-hash. Returns an int with `size*size` bits set based on
    per-pixel greyscale above/below image mean. Stable across resizes and
    minor compression."""
    with Image.open(path) as img:
        g = img.convert("L").resize((size, size), Image.LANCZOS)
    # `tobytes()` on an "L" image is one byte per pixel, same values `getdata()`
    # yielded — and it survives Pillow 14, which drops `Image.getdata`.
    px = g.tobytes()
    avg = sum(px) / len(px)
    bits = 0
    for i, p in enumerate(px):
        if p > avg:
            bits |= 1 << i
    return bits


def hamming_distance(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _stem_key(path: Path) -> str:
    """iOS-style stems are `<YYYYMMDD>_<HHMMSSms>_iOS`. We key on the first 15
    chars (date + time, dropping milliseconds and the `_iOS` suffix) so a HEIC
    and its JPG twin collide even when milliseconds differ by a few units."""
    stem = path.stem
    # Full length is 22 (YYYYMMDD_HHMMSSMMM_iOS); date+time = chars 0-14
    return stem[:15] if len(stem) >= 15 else stem


def collapse_heic_jpg_twins(paths: Iterable[Path]) -> list[Path]:
    """Return the input list with HEIC/JPG same-timestamp pairs collapsed to
    the JPG. Non-iOS filenames pass through untouched."""
    by_key: dict[str, Path] = {}
    passthrough: list[Path] = []
    for p in paths:
        ext = p.suffix.lower()
        if ext in _HEIC_EXTS or ext in _JPG_EXTS:
            key = _stem_key(p)
            existing = by_key.get(key)
            if existing is None:
                by_key[key] = p
            else:
                # Keep JPG over HEIC when both present
                if existing.suffix.lower() in _HEIC_EXTS and ext in _JPG_EXTS:
                    by_key[key] = p
        else:
            passthrough.append(p)
    return sorted([*by_key.values(), *passthrough])


def dedup_perceptual(
    paths: Iterable[Path],
    threshold: int = DEFAULT_HAMMING_THRESHOLD,
) -> list[Path]:
    """Return the input list with near-duplicate images removed. First-seen
    order wins — if you want the highest-quality of each cluster to survive,
    sort `paths` by your quality metric before calling.

    A photo we cannot hash (corrupt, truncated, unsupported codec) is *passed
    through*, not dropped. Dedup runs before the quality gate, and the gate is
    the component that knows how to say "unreadable" — dropping it here made it
    vanish into the caller's `duplicates` reject bucket under a reason that was
    simply false.
    """
    kept: list[Path] = []
    hashes: list[int] = []
    for p in paths:
        try:
            h = average_hash(p)
        except Exception:
            kept.append(p)
            continue
        if any(hamming_distance(h, kh) <= threshold for kh in hashes):
            continue
        kept.append(p)
        hashes.append(h)
    return kept


def dedup_all(
    paths: Iterable[Path],
    perceptual_threshold: int = DEFAULT_HAMMING_THRESHOLD,
) -> list[Path]:
    """Twin collapse followed by perceptual dedup — the usual call site."""
    twin_collapsed = collapse_heic_jpg_twins(paths)
    return dedup_perceptual(twin_collapsed, perceptual_threshold)
