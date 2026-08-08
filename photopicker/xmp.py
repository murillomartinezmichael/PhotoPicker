"""XMP star-rating embed — make cull results visible to Lightroom/Bridge.

Pro tools read `xmp:Rating` (0-5 stars) from an XMP APP1 segment inside the
JPEG itself. Sidecar `.xmp` files do NOT work here: Lightroom ignores sidecars
for JPEG/HEIC (they are RAW-only), and JPEG/HEIC is everything PhotoPicker
reads. So the packet is spliced into the exported *copies* at the byte level —
stdlib only, no re-encode, EXIF untouched, originals never modified.

Rating scale: `rating_for_rank` maps export rank to 5..1 stars by quintile, so
"filter >= 4 stars" in Lightroom shows the top 40% of the culled set and
">= 1 star" shows exactly the exported keepers.
"""
from __future__ import annotations

from pathlib import Path

XMP_MARKER = b"http://ns.adobe.com/xap/1.0/\x00"

_SOI = b"\xff\xd8"
_JPEG_EXTS = {".jpg", ".jpeg"}
# Markers that may appear before image data: APP0..APP15 + COM. The XMP APP1
# goes after this leading run (i.e. after JFIF APP0 / EXIF APP1, per XMP spec).
_LEADING_MARKERS = {*range(0xE0, 0xF0), 0xFE}

_PACKET_TEMPLATE = (
    '<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>\n'
    '<x:xmpmeta xmlns:x="adobe:ns:meta/">\n'
    ' <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">\n'
    '  <rdf:Description rdf:about=""'
    ' xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmp:Rating="{rating}"/>\n'
    ' </rdf:RDF>\n'
    "</x:xmpmeta>\n"
    '<?xpacket end="w"?>'
)


def rating_for_rank(rank: int, total: int) -> int:
    """Map a 1-based export rank to a 5..1 star rating by quintile.

    Rank 1 of 30 -> 5 stars, rank 30 of 30 -> 1 star. Every exported keeper
    gets at least one star — the cull already decided these are the picks.
    """
    if total < 1:
        raise ValueError(f"total must be >= 1, got {total}")
    if not 1 <= rank <= total:
        raise ValueError(f"rank must be in 1..{total}, got {rank}")
    return max(1, 5 - (rank - 1) * 5 // total)


def build_xmp_packet(rating: int) -> bytes:
    """Serialize a minimal XMP packet carrying `xmp:Rating`."""
    if not 0 <= rating <= 5:
        raise ValueError(f"rating must be in 0..5, got {rating}")
    return _PACKET_TEMPLATE.format(rating=rating).encode("utf-8")


def embed_xmp_rating(path: Path, rating: int) -> bool:
    """Splice an `xmp:Rating` APP1 segment into the JPEG at `path`, in place.

    Returns True when the packet was written, False when `path` is not a JPEG
    (PNG/WebP copies pass through untouched — XMP APP1 is JPEG-specific).
    An existing XMP segment is replaced, never duplicated.
    Raises ValueError when a `.jpg` file does not actually contain JPEG bytes.
    """
    if path.suffix.lower() not in _JPEG_EXTS:
        return False
    data = path.read_bytes()
    if data[:2] != _SOI:
        raise ValueError(f"{path.name}: .jpg extension but no JPEG signature")

    packet = build_xmp_packet(rating)
    payload = XMP_MARKER + packet
    segment = b"\xff\xe1" + (len(payload) + 2).to_bytes(2, "big") + payload

    # Walk the leading APPn/COM run to find where the XMP segment belongs,
    # replacing an existing XMP APP1 if one is already there.
    pos = 2
    insert_at = 2
    spans_to_drop: list[tuple[int, int]] = []
    while pos + 4 <= len(data) and data[pos] == 0xFF and data[pos + 1] in _LEADING_MARKERS:
        seg_len = int.from_bytes(data[pos + 2 : pos + 4], "big")
        seg_end = pos + 2 + seg_len
        if data[pos + 1] == 0xE1 and data[pos + 4 : pos + 4 + len(XMP_MARKER)] == XMP_MARKER:
            spans_to_drop.append((pos, seg_end))
        pos = seg_end
        insert_at = pos

    out = bytearray(data)
    for start, end in reversed(spans_to_drop):
        del out[start:end]
        if start < insert_at:
            insert_at -= end - start
    out[insert_at:insert_at] = segment
    path.write_bytes(bytes(out))
    return True
