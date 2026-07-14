from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from photopicker import cli as cli_module
from photopicker.classifier import StubClassifier
from photopicker.profiles import ConfigError, build_from_config, register_profile


def _phase_scores(winner: str, phases: dict[str, str], confidence: float = 0.8):
    remainder = (1.0 - confidence) / max(1, len(phases) - 1)
    return {
        desc: confidence if stage == winner else remainder
        for stage, desc in phases.items()
    }


def test_build_from_config_produces_working_profile(folder_of_distinct_large_images: Path):
    cfg = {
        "name": "test-profile",
        "phases": {
            "empty": "an empty room",
            "midway": "a partially furnished room",
            "done": "a finished furnished room",
        },
        "per_phase_cap": 3,
    }
    profile = build_from_config(cfg)
    assert profile.name == "test-profile"

    paths = sorted(folder_of_distinct_large_images.iterdir())
    scores = {p.name: _phase_scores("empty", cfg["phases"]) for p in paths}
    sel = profile.select(paths, StubClassifier(scores=scores))

    assert set(sel.categorized.keys()) == {"empty", "midway", "done"}
    assert len(sel.categorized["empty"]) <= 3


def test_build_from_config_respects_per_phase_cap(folder_of_distinct_large_images: Path):
    cfg = {
        "name": "cap-test",
        "phases": {"a": "class a", "b": "class b"},
        "per_phase_cap": 2,
    }
    profile = build_from_config(cfg)
    paths = sorted(folder_of_distinct_large_images.iterdir())
    scores = {p.name: _phase_scores("a", cfg["phases"]) for p in paths}
    sel = profile.select(paths, StubClassifier(scores=scores))
    assert len(sel.categorized["a"]) <= 2


def test_build_from_config_default_name_is_custom():
    profile = build_from_config({"phases": {"a": "class a"}})
    assert profile.name == "custom"


def test_build_from_config_missing_phases_raises():
    with pytest.raises(ConfigError):
        build_from_config({"name": "bad"})


def test_build_from_config_empty_phases_raises():
    with pytest.raises(ConfigError):
        build_from_config({"phases": {}})


def test_build_from_config_bad_phase_description_raises():
    with pytest.raises(ConfigError):
        build_from_config({"phases": {"a": ""}})


def test_config_profile_reports_rejects(folder_of_distinct_large_images: Path):
    cfg = {"name": "rr", "phases": {"a": "class a"}}
    profile = build_from_config(cfg)
    paths = sorted(folder_of_distinct_large_images.iterdir())
    scores = {p.name: _phase_scores("a", cfg["phases"]) for p in paths}
    sel = profile.select(paths, StubClassifier(scores=scores))
    assert set(sel.rejected.keys()) == {"duplicates", "unreadable", "too_small", "blurry"}


def test_config_profile_rejects_corrupt_file_as_unreadable(
    folder_of_distinct_large_images: Path,
):
    # Dedup runs before the quality gate. A corrupt file has no perceptual hash,
    # and dedup used to drop it — so it surfaced under "duplicates", which was a
    # false reason. It belongs to the gate, which calls it what it is.
    corrupt = folder_of_distinct_large_images / "corrupt.jpg"
    corrupt.write_bytes(b"not an image")

    cfg = {"name": "corrupt-test", "phases": {"a": "class a"}}
    profile = build_from_config(cfg)
    paths = sorted(folder_of_distinct_large_images.iterdir())
    scores = {p.name: _phase_scores("a", cfg["phases"]) for p in paths}
    sel = profile.select(paths, StubClassifier(scores=scores))

    assert corrupt in sel.rejected["unreadable"]
    assert corrupt not in sel.rejected["duplicates"]


def test_config_profile_chronological_toggle_changes_output_order(
    folder_of_distinct_large_images: Path, monkeypatch
):
    # Prove chronological on vs off produces *different* output ordering by
    # engineering a case where rank-order and time-order disagree.
    from datetime import datetime

    from photopicker.profiles import config_profile as cfg_module

    paths = sorted(folder_of_distinct_large_images.iterdir())

    # Confidence *ascends* with filename order (paths[9] highest-ranked). So
    # rank-desc order is reverse-filename, which is the OPPOSITE of the EXIF
    # order below — giving us two clearly distinguishable output orderings.
    scores: dict[str, dict[str, float]] = {}
    for i, p in enumerate(paths):
        conf = 0.4 + i * 0.05
        scores[p.name] = {"class a": conf}
    classifier = StubClassifier(scores=scores)

    # EXIF times ascend with filename order (paths[0] oldest).
    times = {p: datetime(2026, 1, 1 + i) for i, p in enumerate(paths)}
    monkeypatch.setattr(cfg_module, "get_capture_time", lambda p: times.get(p))

    def _build(chronological: bool):
        return build_from_config(
            {
                "name": f"c-{chronological}",
                "phases": {"a": "class a"},
                "chronological": chronological,
            }
        )

    sel_on = _build(True).select(paths, classifier)
    sel_off = _build(False).select(paths, classifier)

    on_order = [p.name for p in sel_on.categorized["a"]]
    off_order = [p.name for p in sel_off.categorized["a"]]
    # Same set of picks, different order.
    assert set(on_order) == set(off_order)
    if len(on_order) > 1:
        assert on_order == sorted(on_order), "chronological=True must sort ascending by filename (= EXIF here)"
    # Off-mode order is rank-based; since rank descends with filename, off_order
    # should NOT be sorted ascending when there's more than one pick.
    if len(off_order) > 1:
        assert off_order != sorted(off_order)


def _patch_cli_classifier(monkeypatch):
    original = cli_module.pick_photos

    def patched(folder, profile_name, classifier=None):
        return original(folder, profile_name, classifier=classifier or StubClassifier())

    monkeypatch.setattr(cli_module, "pick_photos", patched)


def test_cli_config_flag_end_to_end(
    folder_of_distinct_large_images: Path, tmp_path: Path, monkeypatch
):
    _patch_cli_classifier(monkeypatch)
    cfg_file = tmp_path / "profile.json"
    cfg_file.write_text(
        json.dumps(
            {
                "name": "my-project",
                "phases": {
                    "before": "an empty scene",
                    "after": "a finished scene",
                },
                "per_phase_cap": 4,
            }
        )
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_distinct_large_images),
            "--config", str(cfg_file),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Profile: my-project" in result.output


def test_cli_config_missing_phases_fails_cleanly(
    folder_of_images: Path, tmp_path: Path, monkeypatch
):
    _patch_cli_classifier(monkeypatch)
    bad_cfg = tmp_path / "bad.json"
    bad_cfg.write_text(json.dumps({"name": "broken"}))

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--config", str(bad_cfg),
        ],
    )
    assert result.exit_code != 0
    assert "Invalid config" in result.output


def test_cli_config_invalid_json_fails_cleanly(
    folder_of_images: Path, tmp_path: Path, monkeypatch
):
    _patch_cli_classifier(monkeypatch)
    bad_cfg = tmp_path / "bad.json"
    bad_cfg.write_text("{ this is not json")

    runner = CliRunner()
    result = runner.invoke(
        cli_module.main,
        [
            "--folder", str(folder_of_images),
            "--config", str(bad_cfg),
        ],
    )
    assert result.exit_code != 0
    assert "Failed to read config" in result.output


def test_cli_requires_profile_or_config(folder_of_images: Path):
    runner = CliRunner()
    result = runner.invoke(
        cli_module.main, ["--folder", str(folder_of_images)]
    )
    assert result.exit_code != 0
    assert "required" in result.output.lower()


def test_register_profile_makes_it_discoverable():
    profile = build_from_config(
        {"name": "onboarding-demo", "phases": {"a": "class a"}}
    )
    register_profile(profile)
    from photopicker.profiles import get_profile, list_profiles

    assert "onboarding-demo" in list_profiles()
    assert get_profile("onboarding-demo") is profile
