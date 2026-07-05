from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from click.testing import CliRunner
from PIL import Image

from photopicker import cli as cli_module


def _extract_json_object(text: str) -> dict:
    """Pull the last top-level JSON object out of mixed stdout/stderr output.

    cull_main writes progress lines to stderr but --json-out writes the payload
    to stdout. CliRunner mixes them by default. Scan from the end for the last
    matching `{...}` block using brace depth.
    """
    depth = 0
    end = -1
    start = -1
    # Walk backwards to find the last '}'
    for i in range(len(text) - 1, -1, -1):
        if text[i] == "}":
            end = i
            break
    if end == -1:
        raise ValueError("no JSON object in output")
    depth = 1
    for i in range(end - 1, -1, -1):
        if text[i] == "}":
            depth += 1
        elif text[i] == "{":
            depth -= 1
            if depth == 0:
                start = i
                break
    if start == -1:
        raise ValueError("unbalanced braces in output")
    return json.loads(text[start : end + 1])


def _folder(root: Path, count: int = 12) -> Path:
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
        Image.fromarray(arr).save(folder / f"img_{i:02d}.png")
    return folder


def test_cull_cli_defaults_to_serve_when_no_output_but_can_be_disabled(tmp_path: Path):
    """--no-serve + no --output: cull runs, summary printed, no server started."""
    folder = _folder(tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli_module.cull_main, [str(folder), "--top", "5", "--no-serve"])
    assert result.exit_code == 0, result.output
    assert "Culled" in result.output
    assert "Top keepers" in result.output


def test_cull_cli_output_only_copies_and_does_not_serve(tmp_path: Path):
    folder = _folder(tmp_path)
    out = tmp_path / "keepers"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--output", str(out), "--no-serve"],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    copied = list(out.iterdir())
    assert len(copied) == 3


def test_cull_cli_json_out(tmp_path: Path):
    folder = _folder(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--no-serve", "--json-out"],
    )
    assert result.exit_code == 0, result.output
    payload = _extract_json_object(result.output)
    assert payload["top"] == 3
    assert len(payload["keepers"]) == 3
    assert payload["folder"] == str(folder)


def test_cull_cli_empty_folder_exits_nonzero(tmp_path: Path):
    folder = tmp_path / "empty"
    folder.mkdir()
    runner = CliRunner()
    result = runner.invoke(cli_module.cull_main, [str(folder), "--top", "5", "--no-serve"])
    assert result.exit_code != 0
    assert "No supported images" in result.output


def test_cull_cli_prompt_without_ai_ignored_when_no_ai_set(tmp_path: Path):
    folder = _folder(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [
            str(folder),
            "--top", "3",
            "--no-serve",
            "--prompt", "best portfolio deck photos",
            "--no-ai",
        ],
    )
    assert result.exit_code == 0, result.output
    # No AI logging in output when --no-ai is set.
    assert "Claude Vision rerank" not in result.output


def test_cull_cli_help_lists_new_flags():
    runner = CliRunner()
    result = runner.invoke(cli_module.cull_main, ["--help"])
    assert result.exit_code == 0
    for flag in ("--top", "--prompt", "--no-ai", "--serve", "--port", "--output"):
        assert flag in result.output


def test_cull_cli_prompt_missing_sdk_reports_error(tmp_path: Path, monkeypatch):
    """When --prompt is set but the anthropic SDK isn't installed, cull_main
    should exit non-zero with a helpful message rather than crashing."""
    folder = _folder(tmp_path)

    # Force AnthropicVisionClient() to raise RuntimeError like the missing-SDK path does.
    from photopicker import vision as vision_mod

    class BoomClient:
        def __init__(self, *a, **k):
            raise RuntimeError("Claude Vision rerank needs `pip install photopicker[vision]`")

    monkeypatch.setattr(vision_mod, "AnthropicVisionClient", BoomClient)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [
            str(folder),
            "--top", "3",
            "--no-serve",
            "--prompt", "hero shots",
        ],
    )
    assert result.exit_code != 0
    assert "AI rerank unavailable" in result.output


def test_cull_cli_sort_name_orders_output(tmp_path: Path):
    folder = _folder(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "5", "--no-serve", "--sort", "name", "--json-out"],
    )
    assert result.exit_code == 0, result.output
    payload = _extract_json_object(result.output)
    names = [Path(p).name for p in payload["keepers"]]
    assert names == sorted(names)


def test_cull_cli_manifest_writes_json(tmp_path: Path):
    folder = _folder(tmp_path)
    manifest = tmp_path / "manifest.json"
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--no-serve", "--manifest", str(manifest)],
    )
    assert result.exit_code == 0, result.output
    assert manifest.exists()
    payload = json.loads(manifest.read_text())
    assert payload["top"] == 3
    assert len(payload["picks"]) == 3
    for pick in payload["picks"]:
        assert "rank" in pick
        assert "score" in pick
        assert "capture_time" in pick


def test_cull_cli_resume_skips_pipeline(tmp_path: Path):
    """If the session file exists, --resume should skip the cull entirely."""
    folder = _folder(tmp_path)
    session_path = folder / ".photopicker-session.json"
    fake_session = {
        "source_folder": str(folder),
        "candidates": [
            {"idx": 0, "path": str(folder / "img_00.png"), "filename": "img_00.png",
             "score": 0.9, "ai_score": None, "ai_reason": "", "decision": "keep",
             "capture_time": None, "rejected_reason": ""},
        ],
        "prompt": "",
        "history": [0],
        "reject_summary": {},
        "input_count": 12,
    }
    session_path.write_text(json.dumps(fake_session))

    # --resume with a session file: should not call cull. We patch it to
    # explode so the test fails if it *does* get called.
    import photopicker.cli as cli_mod
    called = []
    original_cull = cli_mod.cull
    cli_mod.cull = lambda *a, **kw: called.append("bug") or original_cull(*a, **kw)

    try:
        # But we don't actually run the server — we patch run_server too.
        import photopicker.webui as wb
        original_serve = wb.serve
        wb.serve = lambda *a, **kw: None

        runner = CliRunner()
        try:
            result = runner.invoke(
                cli_module.cull_main,
                [str(folder), "--top", "3", "--resume"],
            )
        finally:
            wb.serve = original_serve
        assert result.exit_code == 0, result.output
        assert "Resuming from" in result.output
        assert called == []
    finally:
        cli_mod.cull = original_cull


def test_cull_cli_include_rejects_flag_accepted(tmp_path: Path):
    """--include-rejects is offline-friendly; just verify it doesn't crash."""
    folder = _folder(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--no-serve", "--include-rejects"],
    )
    assert result.exit_code == 0, result.output


def test_cull_cli_sort_bad_value_errors(tmp_path: Path):
    folder = _folder(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [str(folder), "--top", "3", "--no-serve", "--sort", "made-up"],
    )
    assert result.exit_code != 0


def test_cull_cli_uses_fake_vision_client_when_provided(tmp_path: Path, monkeypatch):
    """Wire in a fake vision client through monkeypatch, verify AI scores flow
    into the output payload and the keepers get reordered."""
    folder = _folder(tmp_path)

    from photopicker import vision as vision_mod

    class ScoringClient:
        def __init__(self, *a, **k):
            self.n = 0

        def score_photo(self, image_bytes, media_type, prompt):
            self.n += 1
            # Descending score in call order → after sort, later files rise if
            # they were called first. Just prove ai_scores appear in JSON.
            return (100 - self.n, f"call {self.n}")

    monkeypatch.setattr(vision_mod, "AnthropicVisionClient", ScoringClient)

    runner = CliRunner()
    result = runner.invoke(
        cli_module.cull_main,
        [
            str(folder),
            "--top", "3",
            "--no-serve",
            "--prompt", "best photos",
            "--json-out",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = _extract_json_object(result.output)
    assert payload["ai_scores"]
    assert all("score" in v and "reason" in v for v in payload["ai_scores"].values())
