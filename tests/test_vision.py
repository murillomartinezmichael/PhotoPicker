from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photopicker.vision import (
    VisionScore,
    parse_vision_reply,
    rerank,
)


def _make_image(root: Path, name: str, seed: int = 0) -> Path:
    p = root / name
    arr = np.full((600, 600, 3), 128, dtype=np.uint8)
    arr[seed % 500 : (seed % 500) + 100, :] = 255
    Image.fromarray(arr).save(p)
    return p


class FakeClient:
    def __init__(self, scores: dict[str, tuple[int, str]] | None = None) -> None:
        self.scores = scores or {}
        self.calls: list[tuple[int, str, str]] = []

    def score_photo(self, image_bytes, media_type, prompt):
        self.calls.append((len(image_bytes), media_type, prompt))
        # Fake scores keyed by content — we don't have the path here, so use
        # length modulo as a stable pseudo-key. Callers seed via `scores`.
        for key, val in self.scores.items():
            if key in prompt or key == "_default":
                return val
        return 50, "neutral"


# --- parse_vision_reply ------------------------------------------------------


def test_parse_vision_reply_clean_json():
    score, reason = parse_vision_reply('{"score": 87, "reason": "great composition"}')
    assert score == 87
    assert reason == "great composition"


def test_parse_vision_reply_extracts_from_prose():
    text = 'Here is my rating: {"score": 42, "reason": "meh"} — done.'
    score, reason = parse_vision_reply(text)
    assert score == 42
    assert reason == "meh"


def test_parse_vision_reply_clamps_out_of_range():
    score, _ = parse_vision_reply('{"score": 250, "reason": "off"}')
    assert score == 100
    score, _ = parse_vision_reply('{"score": -50, "reason": "off"}')
    assert score == 0


def test_parse_vision_reply_handles_non_numeric_score():
    score, reason = parse_vision_reply('{"score": "high", "reason": "words"}')
    assert score == 0
    assert reason == "words"


def test_parse_vision_reply_no_json_returns_zero_and_snippet():
    score, reason = parse_vision_reply("model refused to score this")
    assert score == 0
    assert "model refused" in reason


def test_parse_vision_reply_empty_string():
    score, reason = parse_vision_reply("")
    assert score == 0
    assert reason == ""


def test_parse_vision_reply_broken_json():
    score, reason = parse_vision_reply("{not really json}")
    assert score == 0
    assert "not really json" in reason


# --- rerank ------------------------------------------------------------------


def test_rerank_orders_by_score_desc(tmp_path: Path):
    a = _make_image(tmp_path, "a.png", seed=1)
    b = _make_image(tmp_path, "b.png", seed=2)
    c = _make_image(tmp_path, "c.png", seed=3)

    call_count = {"n": 0}

    class RankedClient:
        def score_photo(self, image_bytes, media_type, prompt):
            call_count["n"] += 1
            # Return decreasing scores in call order
            return (100 - (call_count["n"] * 10), f"call {call_count['n']}")

    client = RankedClient()
    results = rerank([a, b, c], prompt="best photo", client=client, max_workers=1)

    assert len(results) == 3
    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


def test_rerank_top_n_truncates(tmp_path: Path):
    paths = [_make_image(tmp_path, f"x{i}.png", seed=i) for i in range(5)]
    client = FakeClient({"_default": (55, "ok")})

    results = rerank(paths, prompt="prompt", client=client, top_n=2, max_workers=2)

    assert len(results) == 2
    assert all(isinstance(r, VisionScore) for r in results)


def test_rerank_empty_input_returns_empty():
    client = FakeClient()
    results = rerank([], prompt="prompt", client=client)
    assert results == []


def test_rerank_progress_callback_fires(tmp_path: Path):
    paths = [_make_image(tmp_path, f"y{i}.png", seed=i) for i in range(4)]
    client = FakeClient({"_default": (70, "yes")})
    events: list[tuple[int, int]] = []

    rerank(
        paths,
        prompt="prompt",
        client=client,
        max_workers=2,
        progress=lambda d, t: events.append((d, t)),
    )

    assert events[0] == (0, 4)
    assert events[-1][0] == 4
    assert events[-1][1] == 4


def test_rerank_survives_client_error(tmp_path: Path):
    paths = [_make_image(tmp_path, f"z{i}.png", seed=i) for i in range(3)]
    counter = {"n": 0}

    class SometimesBrokenClient:
        def score_photo(self, image_bytes, media_type, prompt):
            counter["n"] += 1
            if counter["n"] == 2:
                raise RuntimeError("model timed out")
            return 60, "ok"

    results = rerank(paths, prompt="prompt", client=SometimesBrokenClient(), max_workers=1)

    assert len(results) == 3
    # One entry should have the error reason.
    error_entries = [r for r in results if "error" in r.reason]
    assert len(error_entries) == 1
    assert error_entries[0].score == 0


def test_rerank_survives_unreadable_input(tmp_path: Path):
    good = _make_image(tmp_path, "good.png", seed=1)
    bad = tmp_path / "not_an_image.png"
    bad.write_bytes(b"not an image")
    client = FakeClient({"_default": (65, "hi")})

    results = rerank([good, bad], prompt="prompt", client=client, max_workers=1)

    # Bad file dropped silently, good file scored.
    assert len(results) == 1
    assert results[0].path == good


def test_rerank_passes_prompt_to_client(tmp_path: Path):
    p = _make_image(tmp_path, "p.png", seed=0)
    client = FakeClient({"deck portfolio": (75, "match")})

    results = rerank([p], prompt="deck portfolio hero shot", client=client, max_workers=1)

    assert len(results) == 1
    assert results[0].score == 75
    assert client.calls
    assert "deck portfolio hero shot" in client.calls[0][2]


def test_anthropic_vision_client_raises_when_sdk_missing(monkeypatch):
    import photopicker.vision as vision_mod

    original_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no anthropic")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    with pytest.raises(RuntimeError, match="\\[vision\\]"):
        vision_mod.AnthropicVisionClient()
