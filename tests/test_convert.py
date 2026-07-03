from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photopicker.convert import (
    copy_or_transcode,
    generate_thumbnails,
    resolve_output_name,
    to_webp,
    transcode_to_jpg,
)


def _write_png(path: Path, size: tuple[int, int] = (256, 256), value: int = 200) -> Path:
    arr = np.full((size[1], size[0], 3), value, dtype=np.uint8)
    Image.fromarray(arr).save(path, "PNG")
    return path


def test_transcode_to_jpg_produces_valid_jpeg(tmp_path: Path):
    src = _write_png(tmp_path / "src.png")
    dest = tmp_path / "out" / "src.jpg"
    result = transcode_to_jpg(src, dest, quality=85)

    assert result == dest
    assert dest.exists()
    with Image.open(dest) as img:
        assert img.format == "JPEG"
        assert img.size == (256, 256)


def test_transcode_creates_parent_directories(tmp_path: Path):
    src = _write_png(tmp_path / "src.png")
    dest = tmp_path / "a" / "b" / "c" / "x.jpg"
    transcode_to_jpg(src, dest)
    assert dest.exists()


def test_copy_or_transcode_heic_extension_becomes_jpg(tmp_path: Path):
    # PIL reads by content (PNG bytes), so a .heic extension exercises the
    # transcode branch without requiring real HEIC data on disk.
    src = _write_png(tmp_path / "fake_iphone.heic")
    dest_dir = tmp_path / "out" / "before"

    result = copy_or_transcode(src, dest_dir, convert_heic=True)

    assert result.suffix == ".jpg"
    assert result.name == "fake_iphone.jpg"
    assert result.exists()
    with Image.open(result) as img:
        assert img.format == "JPEG"


def test_copy_or_transcode_can_be_disabled(tmp_path: Path):
    src = _write_png(tmp_path / "fake.heic")
    dest_dir = tmp_path / "out"

    result = copy_or_transcode(src, dest_dir, convert_heic=False)

    # Byte-for-byte copy preserving the .heic extension.
    assert result.suffix == ".heic"
    assert result.name == "fake.heic"
    assert result.read_bytes() == src.read_bytes()


def test_copy_or_transcode_non_heic_passes_through(tmp_path: Path):
    src = _write_png(tmp_path / "photo.png")
    dest_dir = tmp_path / "out"

    result = copy_or_transcode(src, dest_dir, convert_heic=True)

    assert result.name == "photo.png"
    assert result.read_bytes() == src.read_bytes()


def test_copy_or_transcode_jpg_passes_through(tmp_path: Path):
    src = tmp_path / "photo.jpg"
    arr = np.full((100, 100, 3), 200, dtype=np.uint8)
    Image.fromarray(arr).save(src, "JPEG", quality=90)
    dest_dir = tmp_path / "out"

    result = copy_or_transcode(src, dest_dir, convert_heic=True)

    # JPG stays as JPG, byte-identical copy.
    assert result.name == "photo.jpg"
    assert result.read_bytes() == src.read_bytes()


def test_copy_or_transcode_heif_extension_also_transcodes(tmp_path: Path):
    # `.heif` is the other common extension iOS uses.
    src = _write_png(tmp_path / "img.heif")
    dest_dir = tmp_path / "out"

    result = copy_or_transcode(src, dest_dir, convert_heic=True)

    assert result.suffix == ".jpg"
    assert result.name == "img.jpg"


def test_copy_or_transcode_creates_dest_dir(tmp_path: Path):
    src = _write_png(tmp_path / "photo.png")
    dest_dir = tmp_path / "new" / "deep" / "output"

    result = copy_or_transcode(src, dest_dir, convert_heic=True)
    assert result.exists()
    assert result.parent == dest_dir


def test_copy_or_transcode_uses_target_name_override(tmp_path: Path):
    src = _write_png(tmp_path / "IMG_4231.heic")
    dest_dir = tmp_path / "out" / "before"

    result = copy_or_transcode(
        src, dest_dir, convert_heic=True, target_name="before-01.jpg"
    )
    assert result.name == "before-01.jpg"
    assert result.exists()


def test_copy_or_transcode_target_name_on_non_heic(tmp_path: Path):
    src = _write_png(tmp_path / "photo.png")
    dest_dir = tmp_path / "out"

    result = copy_or_transcode(
        src, dest_dir, convert_heic=True, target_name="renamed.png"
    )
    assert result.name == "renamed.png"
    assert result.exists()


class TestResolveOutputName:
    def test_original_keeps_source_name(self):
        src = Path("/photos/IMG_4231.jpg")
        name = resolve_output_name(
            src, "before", 1, 1, 12, scheme="original", convert_heic=True
        )
        assert name == "IMG_4231.jpg"

    def test_original_with_heic_swaps_extension_when_transcoding(self):
        src = Path("/photos/IMG_4231.heic")
        name = resolve_output_name(
            src, "before", 1, 1, 12, scheme="original", convert_heic=True
        )
        assert name == "IMG_4231.jpg"

    def test_original_with_heic_and_no_transcode_preserves_extension(self):
        src = Path("/photos/IMG_4231.heic")
        name = resolve_output_name(
            src, "before", 1, 1, 12, scheme="original", convert_heic=False
        )
        assert name == "IMG_4231.heic"

    def test_sequential_globally_numbered_with_min_two_digit_pad(self):
        src = Path("/photos/IMG_4231.jpg")
        # 8 total picks → 2-digit padding
        name = resolve_output_name(
            src, "before", 1, 7, 8, scheme="sequential", convert_heic=True
        )
        assert name == "07.jpg"

    def test_sequential_pads_to_total_width(self):
        src = Path("/photos/IMG_4231.jpg")
        # 250 total picks → 3-digit padding
        name = resolve_output_name(
            src, "before", 5, 42, 250, scheme="sequential", convert_heic=True
        )
        assert name == "042.jpg"

    def test_category_rank_prefixes_with_category(self):
        src = Path("/photos/IMG_4231.heic")
        name = resolve_output_name(
            src, "before", 3, 3, 24, scheme="category-rank", convert_heic=True
        )
        assert name == "before-03.jpg"

    def test_category_rank_preserves_source_extension_when_not_transcoding(self):
        src = Path("/photos/photo.png")
        name = resolve_output_name(
            src, "after", 1, 12, 12, scheme="category-rank", convert_heic=True
        )
        assert name == "after-01.png"

    def test_sequential_extension_follows_transcode(self):
        # HEIC + convert → ext becomes .jpg regardless of source.
        src = Path("/photos/IMG_4231.heic")
        name = resolve_output_name(
            src, "any", 1, 1, 10, scheme="sequential", convert_heic=True
        )
        assert name.endswith(".jpg")

    def test_unknown_scheme_raises(self):
        with pytest.raises(ValueError):
            resolve_output_name(
                Path("/x.jpg"),
                "before",
                1,
                1,
                10,
                scheme="alphabetical",
                convert_heic=True,
            )


class TestGenerateThumbnails:
    def _write_wide_png(self, tmp_path: Path, size: tuple[int, int] = (2000, 1500)) -> Path:
        src = tmp_path / "big.png"
        arr = np.full((size[1], size[0], 3), 180, dtype=np.uint8)
        for i in range(0, size[1], 32):
            for j in range(0, size[0], 32):
                if (i // 32 + j // 32) % 2 == 0:
                    arr[i : i + 16, j : j + 16] = 255
        Image.fromarray(arr).save(src, "PNG")
        return src

    def test_generates_a_file_per_requested_width(self, tmp_path: Path):
        src = self._write_wide_png(tmp_path)
        produced = generate_thumbnails(
            src, tmp_path / "out", "before-01", widths=[400, 800, 1200]
        )
        assert set(produced.keys()) == {400, 800, 1200}
        for width, path in produced.items():
            assert path.name == f"before-01-{width}w.jpg"
            assert path.exists()
            with Image.open(path) as img:
                assert img.format == "JPEG"
                assert img.size[0] == width

    def test_preserves_aspect_ratio(self, tmp_path: Path):
        # 2000x1500 → aspect 4:3. A 400w thumbnail must be 400x300.
        src = self._write_wide_png(tmp_path, size=(2000, 1500))
        produced = generate_thumbnails(src, tmp_path / "out", "x", widths=[400])
        with Image.open(produced[400]) as img:
            assert img.size == (400, 300)

    def test_skips_widths_larger_than_source(self, tmp_path: Path):
        # 800px-wide source, request 400/800/1200. Only 400 should land.
        src = self._write_wide_png(tmp_path, size=(800, 600))
        produced = generate_thumbnails(
            src, tmp_path / "out", "x", widths=[400, 800, 1200]
        )
        assert set(produced.keys()) == {400}

    def test_empty_widths_returns_empty(self, tmp_path: Path):
        src = self._write_wide_png(tmp_path)
        assert generate_thumbnails(src, tmp_path / "out", "x", widths=[]) == {}

    def test_creates_dest_dir(self, tmp_path: Path):
        src = self._write_wide_png(tmp_path)
        dest_dir = tmp_path / "new" / "deep"
        generate_thumbnails(src, dest_dir, "x", widths=[400])
        assert dest_dir.exists()

    def test_deduplicates_widths(self, tmp_path: Path):
        src = self._write_wide_png(tmp_path)
        # Duplicate 400 twice — should still only produce one file at 400.
        produced = generate_thumbnails(
            src, tmp_path / "out", "x", widths=[400, 400, 800]
        )
        assert set(produced.keys()) == {400, 800}

    def test_webp_format_produces_webp_files(self, tmp_path: Path):
        src = self._write_wide_png(tmp_path)
        produced = generate_thumbnails(
            src, tmp_path / "out", "hero", widths=[400, 800], fmt="webp"
        )
        assert set(produced.keys()) == {400, 800}
        for width, path in produced.items():
            assert path.name == f"hero-{width}w.webp"
            with Image.open(path) as img:
                assert img.format == "WEBP"

    def test_unknown_fmt_raises(self, tmp_path: Path):
        src = self._write_wide_png(tmp_path)
        with pytest.raises(ValueError):
            generate_thumbnails(
                src, tmp_path / "out", "x", widths=[400], fmt="avif"
            )


class TestToWebp:
    def _write_png(self, path: Path, size: tuple[int, int] = (256, 256)) -> Path:
        arr = np.full((size[1], size[0], 3), 200, dtype=np.uint8)
        Image.fromarray(arr).save(path, "PNG")
        return path

    def test_writes_valid_webp(self, tmp_path: Path):
        src = self._write_png(tmp_path / "src.png")
        dest = tmp_path / "out" / "src.webp"
        result = to_webp(src, dest, quality=80)

        assert result == dest
        with Image.open(dest) as img:
            assert img.format == "WEBP"
            assert img.size == (256, 256)

    def test_creates_parent_dirs(self, tmp_path: Path):
        src = self._write_png(tmp_path / "src.png")
        dest = tmp_path / "a" / "b" / "c" / "src.webp"
        to_webp(src, dest)
        assert dest.exists()

    def test_can_read_heic_extension_input(self, tmp_path: Path):
        # PIL reads by content, so PNG bytes with .heic extension work here too.
        src = self._write_png(tmp_path / "iphone.heic")
        dest = tmp_path / "out" / "iphone.webp"
        to_webp(src, dest)
        with Image.open(dest) as img:
            assert img.format == "WEBP"
