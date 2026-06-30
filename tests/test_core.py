from __future__ import annotations

from pathlib import Path

import pytest

from photopicker.classifier import StubClassifier
from photopicker.core import discover_images, pick_photos


def test_discover_finds_supported(folder_of_images: Path):
    paths = discover_images(folder_of_images)
    assert len(paths) == 10
    assert all(p.suffix == ".png" for p in paths)


def test_discover_skips_unknown_extensions(tmp_path: Path):
    folder = tmp_path / "mixed"
    folder.mkdir()
    (folder / "a.png").write_bytes(b"")
    (folder / "b.txt").write_text("not an image")
    (folder / "c.md").write_text("readme")
    paths = discover_images(folder)
    assert [p.name for p in paths] == ["a.png"]


def test_discover_raises_on_missing_folder(tmp_path: Path):
    with pytest.raises(NotADirectoryError):
        discover_images(tmp_path / "nope")


def test_discover_raises_on_file(sharp_image: Path):
    with pytest.raises(NotADirectoryError):
        discover_images(sharp_image)


def test_pick_photos_with_stub(folder_of_images: Path):
    result = pick_photos(folder_of_images, "default", classifier=StubClassifier())
    assert result.profile == "default"
    assert result.source_folder == folder_of_images
    assert "featured" in result.selection.categorized


def test_pick_photos_summary_contains_categories(folder_of_images: Path):
    result = pick_photos(folder_of_images, "aries", classifier=StubClassifier())
    summary = result.summary()
    assert "before" in summary
    assert "during" in summary
    assert "after" in summary
    assert "others" in summary


def test_pick_photos_accepts_str_path(folder_of_images: Path):
    result = pick_photos(str(folder_of_images), "default", classifier=StubClassifier())
    assert isinstance(result.source_folder, Path)
