from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from click.testing import CliRunner
from PIL import Image

from photopicker import cli as cli_module
from photopicker.classifier import CLIP_INSTALL_HINT, StubClassifier


def _patch_cli_classifier(monkeypatch):
    """Force the CLI to use StubClassifier (no torch download in tests)."""
    original = cli_module.pick_photos

    def patched(folder, profile_name, classifier=None):
        return original(folder, profile_name, classifier=classifier or StubClassifier())

    monkeypatch.setattr(cli_module, "pick_photos", patched)


def test_cli_runs_default_profile(folder_of_images: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--folder", str(folder_of_images), "--profile", "default"],
    )
    assert result.exit_code == 0, result.output
    assert "Profile: default" in result.output
    assert "featured" in result.output


def test_cli_copies_to_output(folder_of_images: Path, tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "aries",
            "--output", str(out_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert out_dir.exists()
    assert (out_dir / "before").exists()
    assert (out_dir / "during").exists()
    assert (out_dir / "after").exists()
    assert (out_dir / "others").exists()
    # At least the 3 stage picks should land in their folders
    assert any((out_dir / "before").iterdir())


def test_cli_json_output(folder_of_images: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--folder", str(folder_of_images), "--profile", "default", "--json-out"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output.split("Copied")[0])
    assert payload["profile"] == "default"
    assert "featured" in payload["selection"]


def test_cli_missing_clip_extra_is_human_readable(folder_of_images: Path, monkeypatch):
    """README's own example (`photopicker --folder X --profile aries`) without
    the [clip] extra must print the install hint and exit 1 — no traceback."""

    def raising(folder, profile_name, classifier=None):
        raise ImportError(CLIP_INSTALL_HINT)

    monkeypatch.setattr(cli_module, "pick_photos", raising)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--folder", str(folder_of_images), "--profile", "aries"],
    )
    assert result.exit_code == 1
    assert "photopicker[clip]" in result.output
    assert "Traceback" not in result.output


def test_cli_unknown_profile(folder_of_images: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--folder", str(folder_of_images), "--profile", "noooope"],
    )
    assert result.exit_code != 0
    assert "Unknown profile" in result.output


def test_cli_missing_folder():
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--folder", "/tmp/does/not/exist/zzz", "--profile", "default"],
    )
    assert result.exit_code != 0


def test_cli_transcodes_heic_to_jpg_on_output(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    # PIL reads by content, so PNG bytes with a .heic extension exercise the
    # transcode branch without requiring real HEIC data on disk.
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    checker = np.full((256, 256, 3), 128, dtype=np.uint8)
    for i in range(0, 256, 16):
        for j in range(0, 256, 16):
            if (i // 16 + j // 16) % 2 == 0:
                checker[i : i + 16, j : j + 16] = 255
    # 8 normal PNGs.
    for i in range(8):
        Image.fromarray(checker).save(src_folder / f"img_{i:02d}.png", "PNG")
    # 2 "iPhone" HEICs.
    Image.fromarray(checker).save(src_folder / "IMG_0001.heic", "PNG")
    Image.fromarray(checker).save(src_folder / "IMG_0002.heic", "PNG")

    out_dir = tmp_path / "out"
    manifest = tmp_path / "manifest.json"

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--manifest", str(manifest),
        ],
    )
    assert result.exit_code == 0, result.output
    # No HEIC files remain in the output.
    heic_survivors = list(out_dir.rglob("*.heic"))
    assert heic_survivors == []
    # transcode counter reported.
    assert "transcoded to JPG" in result.output

    # Manifest carries output_path pointing at the .jpg for HEIC inputs.
    payload = json.loads(manifest.read_text())
    heic_picks = [p for p in payload["picks"] if p["filename"].lower().endswith(".heic")]
    if heic_picks:
        for pick in heic_picks:
            assert pick["output_path"].lower().endswith(".jpg")
            assert pick["output_filename"].lower().endswith(".jpg")


def test_cli_rename_scheme_category_rank_anonymizes(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    # 12 iPhone-looking HEIC files → published as before-01, before-02, ...
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    checker = np.full((256, 256, 3), 128, dtype=np.uint8)
    for i in range(0, 256, 16):
        for j in range(0, 256, 16):
            if (i // 16 + j // 16) % 2 == 0:
                checker[i : i + 16, j : j + 16] = 255
    for i in range(12):
        Image.fromarray(checker).save(src_folder / f"IMG_{4200 + i:04d}.heic", "PNG")

    out_dir = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--manifest", str(manifest),
            "--rename-scheme", "category-rank",
        ],
    )
    assert result.exit_code == 0, result.output
    # No IMG_ names survive in the output tree.
    surviving_img = list(out_dir.rglob("IMG_*"))
    assert surviving_img == []
    # All output files match <category>-NN.jpg.
    for jpg in out_dir.rglob("*.jpg"):
        stem = jpg.stem  # e.g. featured-01
        parts = stem.rsplit("-", 1)
        assert len(parts) == 2
        assert parts[0] in {"featured", "before", "during", "after", "others"}
        assert parts[1].isdigit()
    # Copy log calls out the rename.
    assert "renamed via category-rank" in result.output
    # Manifest output_filename shows the anonymized name, not IMG_*.
    payload = json.loads(manifest.read_text())
    for pick in payload["picks"]:
        assert not pick["output_filename"].startswith("IMG_")


def test_cli_thumbnails_flag_generates_srcset_siblings(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    # Big source images so 400/800 thumbnails fit under the source width.
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    arr = np.full((1500, 2000, 3), 180, dtype=np.uint8)
    for i in range(0, 1500, 32):
        for j in range(0, 2000, 32):
            if (i // 32 + j // 32) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    for i in range(9):
        Image.fromarray(arr).save(src_folder / f"pic_{i:02d}.png", "PNG")

    out_dir = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--manifest", str(manifest),
            "--thumbnails", "400,800",
            "--rename-scheme", "category-rank",
        ],
    )
    assert result.exit_code == 0, result.output
    # Every pick has -400w.jpg and -800w.jpg siblings.
    jpg_400 = list(out_dir.rglob("*-400w.jpg"))
    jpg_800 = list(out_dir.rglob("*-800w.jpg"))
    assert len(jpg_400) == 9
    assert len(jpg_800) == 9
    # thumbnail count reported in copy log.
    assert "thumbnails" in result.output
    # Manifest carries the srcset map per pick.
    payload = json.loads(manifest.read_text())
    for pick in payload["picks"]:
        assert "thumbnails" in pick
        assert set(pick["thumbnails"].keys()) == {"400", "800"}
        for width_str, thumb_name in pick["thumbnails"].items():
            assert thumb_name.endswith(f"-{width_str}w.jpg")


def test_cli_webp_flag_writes_webp_siblings(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    arr = np.full((1500, 2000, 3), 180, dtype=np.uint8)
    for i in range(0, 1500, 32):
        for j in range(0, 2000, 32):
            if (i // 32 + j // 32) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    # .heic extension so HEIC→JPG transcode fires and gives us JPGs to compare against.
    for i in range(9):
        Image.fromarray(arr).save(src_folder / f"pic_{i:02d}.heic", "PNG")

    out_dir = tmp_path / "out"
    manifest = tmp_path / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--manifest", str(manifest),
            "--thumbnails", "400,800",
            "--webp",
            "--rename-scheme", "category-rank",
        ],
    )
    assert result.exit_code == 0, result.output
    # Both formats present at every width.
    for width in ("400w", "800w"):
        assert len(list(out_dir.rglob(f"*-{width}.jpg"))) == 9
        assert len(list(out_dir.rglob(f"*-{width}.webp"))) == 9
    # Main files (non-thumbnail) in both formats.
    all_jpgs = list(out_dir.rglob("*.jpg"))
    all_webps = list(out_dir.rglob("*.webp"))
    main_jpgs = [p for p in all_jpgs if not any(w in p.name for w in ("400w", "800w"))]
    main_webps = [p for p in all_webps if not any(w in p.name for w in ("400w", "800w"))]
    assert len(main_jpgs) == 9
    assert len(main_webps) == 9
    # Copy log calls out the webp count.
    assert "webp" in result.output
    # Manifest carries both format maps per pick.
    payload = json.loads(manifest.read_text())
    for pick in payload["picks"]:
        assert "output_webp_filename" in pick
        assert pick["output_webp_filename"].endswith(".webp")
        assert "thumbnails_webp" in pick
        assert set(pick["thumbnails_webp"].keys()) == {"400", "800"}


def test_cli_webp_without_thumbnails_still_writes_main_webp(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    arr = np.full((512, 512, 3), 128, dtype=np.uint8)
    for i in range(0, 512, 32):
        for j in range(0, 512, 32):
            if (i // 32 + j // 32) % 2 == 0:
                arr[i : i + 16, j : j + 16] = 255
    # HEIC extension → main copy transcodes to .jpg.
    for i in range(9):
        Image.fromarray(arr).save(src_folder / f"pic_{i:02d}.heic", "PNG")

    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--webp",
        ],
    )
    assert result.exit_code == 0, result.output
    # 9 main JPGs + 9 main WebPs, no thumbnails.
    assert len(list(out_dir.rglob("*.jpg"))) == 9
    assert len(list(out_dir.rglob("*.webp"))) == 9


def test_cli_thumbnails_invalid_input(folder_of_images: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "default",
            "--thumbnails", "not-a-number",
        ],
    )
    assert result.exit_code != 0
    assert "comma-separated" in result.output


def test_cli_rename_scheme_sequential_numbers_globally(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    checker = np.full((256, 256, 3), 128, dtype=np.uint8)
    for i in range(0, 256, 16):
        for j in range(0, 256, 16):
            if (i // 16 + j // 16) % 2 == 0:
                checker[i : i + 16, j : j + 16] = 255
    for i in range(10):
        Image.fromarray(checker).save(src_folder / f"raw_{i:02d}.png", "PNG")

    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--rename-scheme", "sequential",
        ],
    )
    assert result.exit_code == 0, result.output
    names = sorted(p.name for p in out_dir.rglob("*.png"))
    # 9 picks (default profile picks top 9), globally numbered 01..09
    assert names == [f"{i:02d}.png" for i in range(1, 10)]


def test_cli_no_convert_heic_preserves_extension(tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    src_folder = tmp_path / "photos"
    src_folder.mkdir()
    checker = np.full((256, 256, 3), 128, dtype=np.uint8)
    for i in range(0, 256, 16):
        for j in range(0, 256, 16):
            if (i // 16 + j // 16) % 2 == 0:
                checker[i : i + 16, j : j + 16] = 255
    for i in range(9):
        Image.fromarray(checker).save(src_folder / f"IMG_{i:04d}.heic", "PNG")

    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(src_folder),
            "--profile", "default",
            "--output", str(out_dir),
            "--no-convert-heic",
        ],
    )
    assert result.exit_code == 0, result.output
    # HEIC files kept as-is.
    heic_survivors = list(out_dir.rglob("*.heic"))
    assert len(heic_survivors) > 0
    assert "transcoded" not in result.output


def test_cli_writes_manifest(folder_of_images: Path, tmp_path: Path, monkeypatch):
    _patch_cli_classifier(monkeypatch)
    manifest_path = tmp_path / "out" / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "default",
            "--manifest", str(manifest_path),
        ],
    )
    assert result.exit_code == 0, result.output
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["profile"] == "default"
    assert manifest["source"] == str(folder_of_images)
    assert len(manifest["picks"]) == 9
    assert all("rank" in p for p in manifest["picks"])
    assert f"Wrote manifest to {manifest_path}" in result.output


# --- --dry-run ---------------------------------------------------------------


def test_cli_dry_run_prints_prefix_and_does_not_need_patched_classifier(
    folder_of_images: Path,
):
    # Deliberately do NOT patch the classifier — --dry-run must skip CLIP
    # entirely by using StubClassifier internally. If dry-run tried to
    # download the CLIP model, this test would time out.
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--folder", str(folder_of_images), "--profile", "default", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "[dry-run] CLIP skipped" in result.output
    # Summary still runs — user can eyeball the pick shape.
    assert "Profile: default" in result.output
    assert "featured" in result.output


def test_cli_dry_run_does_not_write_to_output(
    folder_of_images: Path, tmp_path: Path,
):
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "default",
            "--output", str(out_dir),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    # No copies written.
    assert not out_dir.exists()
    # But the CLI describes what it would have done.
    assert "[dry-run] Would copy:" in result.output
    assert str(out_dir) in result.output


def test_cli_dry_run_does_not_write_manifest(
    folder_of_images: Path, tmp_path: Path,
):
    manifest_path = tmp_path / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "default",
            "--manifest", str(manifest_path),
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert not manifest_path.exists()
    assert f"[dry-run] Would write manifest to {manifest_path}" in result.output


def test_cli_dry_run_notes_thumbnails_webp_rename_scheme_in_would_copy_line(
    folder_of_images: Path, tmp_path: Path,
):
    out_dir = tmp_path / "out"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "default",
            "--output", str(out_dir),
            "--thumbnails", "400,800",
            "--webp",
            "--rename-scheme", "category-rank",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[dry-run] Would copy:" in result.output
    assert "thumbnails at widths 400,800" in result.output
    assert "webp siblings" in result.output
    assert "rename via category-rank" in result.output


def test_cli_dry_run_json_output_still_prints_pick_payload(
    folder_of_images: Path,
):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--profile", "default",
            "--json-out",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    # JSON payload is still emitted (nothing about --output/manifest).
    assert '"profile": "default"' in result.output
    assert '"selection"' in result.output


def test_cli_list_profiles_prints_names_and_exits():
    from photopicker.profiles import list_profiles

    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["--list-profiles"])
    assert result.exit_code == 0, result.output
    expected = list_profiles()
    assert expected, "list_profiles() must return at least one built-in profile"
    for name in expected:
        assert name in result.output


def test_cli_list_profiles_skips_folder_requirement():
    # --folder is required=True; --list-profiles must short-circuit before that
    # validation fires, so operators can discover profiles without a folder path.
    runner = CliRunner()
    result = runner.invoke(cli_module.main, ["--list-profiles"])
    assert result.exit_code == 0
    assert "Missing option" not in result.output
    assert "Error" not in result.output


def test_cli_list_profiles_ignores_other_flags():
    # is_eager on --list-profiles means it fires before other options parse,
    # so pairing it with a nonsense --profile still exits cleanly.
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        ["--list-profiles", "--profile", "does-not-exist"],
    )
    assert result.exit_code == 0
    assert "does-not-exist" not in result.output.split("\n")[0]
