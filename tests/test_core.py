from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from photopicker import core as core_module
from photopicker.classifier import StubClassifier
from photopicker.core import PhotoPick, discover_images, pick_photos
from photopicker.profiles.registry import Selection


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


def test_manifest_shape(folder_of_images: Path, monkeypatch):
    result = pick_photos(folder_of_images, "default", classifier=StubClassifier())
    manifest = result.to_manifest()

    assert manifest["profile"] == "default"
    assert manifest["source"] == str(folder_of_images)
    assert "generated_at" in manifest
    assert manifest["reject_counts"] == {}
    assert isinstance(manifest["picks"], list)
    assert len(manifest["picks"]) == 9

    for i, pick in enumerate(manifest["picks"]):
        assert pick["category"] == "featured"
        assert pick["rank"] == i + 1
        assert pick["filename"].endswith(".png")
        assert pick["dimensions"] == {"width": 256, "height": 256}
        # Fixture PNGs have no EXIF.
        assert pick["capture_time"] is None


def test_manifest_ranks_reset_per_category(folder_of_images: Path):
    result = pick_photos(folder_of_images, "aries", classifier=StubClassifier())
    manifest = result.to_manifest()

    by_cat: dict[str, list[int]] = {}
    for pick in manifest["picks"]:
        by_cat.setdefault(pick["category"], []).append(pick["rank"])
    for _cat, ranks in by_cat.items():
        assert ranks == list(range(1, len(ranks) + 1)), (
            "rank must restart at 1 within each category"
        )


def test_manifest_capture_time_serialized_when_present(monkeypatch, sharp_image: Path):
    monkeypatch.setattr(
        core_module, "get_capture_time", lambda p: datetime(2026, 3, 15, 12, 30)
    )
    pick = PhotoPick(
        profile="default",
        selection=Selection(categorized={"featured": [sharp_image]}),
        source_folder=sharp_image.parent,
    )
    manifest = pick.to_manifest()
    assert manifest["picks"][0]["capture_time"] == "2026-03-15T12:30:00"


def test_manifest_output_paths_thread_through():
    src = Path("/photos/IMG_0001.heic")
    dest = Path("/site/img/before/IMG_0001.jpg")
    pick = PhotoPick(
        profile="aries-gallery",
        selection=Selection(categorized={"before": [src]}),
        source_folder=Path("/photos"),
    )
    manifest = pick.to_manifest(output_paths={src: dest})
    entry = manifest["picks"][0]
    assert entry["output_path"] == str(dest)
    assert entry["output_filename"] == "IMG_0001.jpg"
    # Source references still intact.
    assert entry["filename"] == "IMG_0001.heic"
    assert entry["path"] == str(src)


def test_manifest_webp_fields_thread_through():
    src = Path("/photos/IMG_0001.heic")
    jpg = Path("/site/img/before/before-01.jpg")
    webp = Path("/site/img/before/before-01.webp")
    webp_thumbs = {
        400: Path("/site/img/before/before-01-400w.webp"),
        800: Path("/site/img/before/before-01-800w.webp"),
    }
    pick = PhotoPick(
        profile="aries-gallery",
        selection=Selection(categorized={"before": [src]}),
        source_folder=Path("/photos"),
    )
    manifest = pick.to_manifest(
        output_paths={src: jpg},
        webp_paths={src: webp},
        thumbnails_webp={src: webp_thumbs},
    )
    entry = manifest["picks"][0]
    assert entry["output_filename"] == "before-01.jpg"
    assert entry["output_webp_filename"] == "before-01.webp"
    assert entry["output_webp"] == str(webp)
    assert entry["thumbnails_webp"] == {
        "400": "before-01-400w.webp",
        "800": "before-01-800w.webp",
    }


def test_manifest_no_webp_fields_when_none_provided():
    src = Path("a.jpg")
    pick = PhotoPick(
        profile="default",
        selection=Selection(categorized={"featured": [src]}),
        source_folder=Path("/x"),
    )
    entry = pick.to_manifest()["picks"][0]
    assert "output_webp" not in entry
    assert "output_webp_filename" not in entry
    assert "thumbnails_webp" not in entry


def test_manifest_thumbnails_map_survives_serialization():
    src = Path("/photos/IMG_0001.heic")
    dest = Path("/site/img/before/before-01.jpg")
    thumbs = {
        src: {
            400: Path("/site/img/before/before-01-400w.jpg"),
            800: Path("/site/img/before/before-01-800w.jpg"),
            1200: Path("/site/img/before/before-01-1200w.jpg"),
        }
    }
    pick = PhotoPick(
        profile="aries-gallery",
        selection=Selection(categorized={"before": [src]}),
        source_folder=Path("/photos"),
    )
    manifest = pick.to_manifest(output_paths={src: dest}, thumbnails=thumbs)
    entry = manifest["picks"][0]
    assert entry["thumbnails"] == {
        "400": "before-01-400w.jpg",
        "800": "before-01-800w.jpg",
        "1200": "before-01-1200w.jpg",
    }


def test_manifest_no_thumbnails_field_when_none_provided():
    src = Path("a.jpg")
    pick = PhotoPick(
        profile="default",
        selection=Selection(categorized={"featured": [src]}),
        source_folder=Path("/x"),
    )
    entry = pick.to_manifest()["picks"][0]
    assert "thumbnails" not in entry


def test_manifest_no_output_paths_by_default():
    pick = PhotoPick(
        profile="default",
        selection=Selection(categorized={"featured": [Path("a.jpg")]}),
        source_folder=Path("/x"),
    )
    entry = pick.to_manifest()["picks"][0]
    assert "output_path" not in entry
    assert "output_filename" not in entry


def test_manifest_reject_counts_propagate():
    pick = PhotoPick(
        profile="aries-gallery",
        selection=Selection(
            categorized={"before": []},
            rejected={"duplicates": [Path("a.jpg"), Path("b.jpg")]},
        ),
        source_folder=Path("/x"),
    )
    manifest = pick.to_manifest()
    assert manifest["reject_counts"] == {"duplicates": 2}
    assert "rejected" not in manifest, "manifest should not leak reject paths"
