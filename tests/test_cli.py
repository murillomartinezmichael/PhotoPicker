from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from photopicker import cli as cli_module
from photopicker.classifier import StubClassifier


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
