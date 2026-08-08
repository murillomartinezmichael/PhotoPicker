from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from click.testing import CliRunner
from PIL import Image

from photopicker import cli as cli_module
from photopicker.xmp import (
    XMP_MARKER,
    build_xmp_packet,
    embed_xmp_rating,
    rating_for_rank,
)


def _jpg(root: Path, name: str = "a.jpg", seed: int = 0, exif: bool = False) -> Path:
    p = root / name
    arr = np.full((600, 600, 3), 128, dtype=np.uint8)
    arr[seed % 500 : (seed % 500) + 100, :] = 255
    img = Image.fromarray(arr)
    if exif:
        ex = Image.Exif()
        ex[0x010F] = "photopicker-test"  # Make
        img.save(p, exif=ex)
    else:
        img.save(p)
    return p


# --- rating_for_rank ---------------------------------------------------------


def test_rating_for_rank_quintiles_over_30():
    assert rating_for_rank(1, 30) == 5
    assert rating_for_rank(6, 30) == 5
    assert rating_for_rank(7, 30) == 4
    assert rating_for_rank(30, 30) == 1


def test_rating_for_rank_single_photo_gets_five_stars():
    assert rating_for_rank(1, 1) == 5


def test_rating_for_rank_always_at_least_one_star():
    for total in (1, 3, 5, 30, 100):
        for rank in range(1, total + 1):
            assert 1 <= rating_for_rank(rank, total) <= 5


def test_rating_for_rank_rejects_bad_inputs():
    with pytest.raises(ValueError):
        rating_for_rank(0, 5)
    with pytest.raises(ValueError):
        rating_for_rank(6, 5)
    with pytest.raises(ValueError):
        rating_for_rank(1, 0)


# --- build_xmp_packet --------------------------------------------------------


def test_packet_carries_rating_and_xpacket_frame():
    packet = build_xmp_packet(4)
    assert b'xmp:Rating="4"' in packet
    assert b"<?xpacket begin=" in packet
    assert b'<?xpacket end="w"?>' in packet


def test_packet_rejects_out_of_range_rating():
    with pytest.raises(ValueError):
        build_xmp_packet(6)
    with pytest.raises(ValueError):
        build_xmp_packet(-1)


# --- embed_xmp_rating --------------------------------------------------------


def test_embed_writes_xmp_app1_and_file_still_decodes(tmp_path: Path):
    p = _jpg(tmp_path, seed=1)
    assert embed_xmp_rating(p, 5) is True
    data = p.read_bytes()
    assert XMP_MARKER in data
    assert b'xmp:Rating="5"' in data
    with Image.open(p) as img:  # splice must not corrupt the JPEG
        img.load()
        assert img.size == (600, 600)


def test_embed_preserves_exif(tmp_path: Path):
    p = _jpg(tmp_path, seed=2, exif=True)
    embed_xmp_rating(p, 3)
    with Image.open(p) as img:
        assert img.getexif()[0x010F] == "photopicker-test"


def test_embed_twice_replaces_instead_of_duplicating(tmp_path: Path):
    p = _jpg(tmp_path, seed=3)
    embed_xmp_rating(p, 2)
    embed_xmp_rating(p, 5)
    data = p.read_bytes()
    assert data.count(XMP_MARKER) == 1
    assert b'xmp:Rating="5"' in data
    assert b'xmp:Rating="2"' not in data


def test_embed_skips_non_jpeg(tmp_path: Path):
    p = tmp_path / "a.png"
    Image.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(p)
    before = p.read_bytes()
    assert embed_xmp_rating(p, 5) is False
    assert p.read_bytes() == before


def test_embed_rejects_jpg_extension_without_jpeg_bytes(tmp_path: Path):
    p = tmp_path / "fake.jpg"
    p.write_bytes(b"definitely not a jpeg")
    with pytest.raises(ValueError):
        embed_xmp_rating(p, 5)


# --- CLI wiring --------------------------------------------------------------


def _jpg_folder(root: Path, count: int = 6) -> Path:
    folder = root / "shoot"
    folder.mkdir()
    for i in range(count):
        arr = np.full((900, 900, 3), 128, dtype=np.uint8)
        row_off = (i * 90) % 900
        arr[row_off : row_off + 200, :] = 255
        for r in range(0, 900, 16):
            for c in range(0, 900, 16):
                if (r // 16 + c // 16) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = min(255, 200 + i * 5)
        Image.fromarray(arr).save(folder / f"img_{i:02d}.jpg")
    return folder


def test_cull_cli_xmp_embeds_ratings_into_output_copies(tmp_path: Path):
    folder = _jpg_folder(tmp_path)
    out = tmp_path / "keepers"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--output", str(out), "--no-serve", "--xmp"],
    )
    assert result.exit_code == 0, result.output
    assert "Embedded xmp:Rating into 3/3 JPEG copies" in result.output
    for copy in out.glob("*.jpg"):
        assert XMP_MARKER in copy.read_bytes()
    # Originals stay untouched — the whole point of embedding into copies.
    for original in folder.glob("*.jpg"):
        assert XMP_MARKER not in original.read_bytes()


def test_cull_cli_without_xmp_leaves_copies_clean(tmp_path: Path):
    folder = _jpg_folder(tmp_path)
    out = tmp_path / "keepers"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--output", str(out), "--no-serve"],
    )
    assert result.exit_code == 0, result.output
    for copy in out.glob("*.jpg"):
        assert XMP_MARKER not in copy.read_bytes()
