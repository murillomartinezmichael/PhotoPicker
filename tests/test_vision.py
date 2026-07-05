from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photopicker.vision import (
    VisionRetryError,
    VisionScore,
    _backoff_delay,
    _is_retryable,
    _resolve_max_attempts,
    call_with_retry,
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


def test_call_with_retry_succeeds_first_try():
    calls = []

    def _fn():
        calls.append(1)
        return 42, "ok"

    score, reason = call_with_retry(_fn, sleep=lambda _: None)
    assert score == 42 and reason == "ok"
    assert len(calls) == 1


def test_call_with_retry_retries_transient_then_succeeds():
    calls = []
    sleeps = []
    events = []

    def _fn():
        calls.append(1)
        if len(calls) < 3:
            raise TimeoutError("transient")
        return 88, "ok now"

    score, reason = call_with_retry(
        _fn,
        max_attempts=5,
        sleep=lambda d: sleeps.append(d),
        on_retry=lambda a, e, d: events.append((a, type(e).__name__, d)),
    )
    assert score == 88
    assert len(calls) == 3
    assert len(sleeps) == 2
    assert all(e[1] == "TimeoutError" for e in events)


def test_call_with_retry_gives_up_after_max_attempts():
    def _fn():
        raise ConnectionError("boom")

    with pytest.raises(VisionRetryError) as exc_info:
        call_with_retry(_fn, max_attempts=3, sleep=lambda _: None)
    assert exc_info.value.attempts == 3
    assert isinstance(exc_info.value.last_error, ConnectionError)


def test_call_with_retry_does_not_retry_non_retryable():
    calls = []

    def _fn():
        calls.append(1)
        raise ValueError("bad input")

    with pytest.raises(VisionRetryError):
        call_with_retry(_fn, max_attempts=5, sleep=lambda _: None)
    # ValueError is not retryable → only one attempt should have been made.
    assert len(calls) == 1


def test_call_with_retry_never_retries_keyboard_interrupt():
    def _fn():
        raise KeyboardInterrupt()

    with pytest.raises(VisionRetryError):
        call_with_retry(_fn, max_attempts=5, sleep=lambda _: None)


def test_is_retryable_network_errors():
    assert _is_retryable(TimeoutError("t"))
    assert _is_retryable(ConnectionError("c"))
    assert not _is_retryable(ValueError("v"))
    assert not _is_retryable(KeyboardInterrupt())
    assert not _is_retryable(SystemExit())


def test_backoff_delay_grows_and_caps():
    # No jitter for a deterministic assertion.
    d0 = _backoff_delay(0, base=1.0, cap=10.0, jitter=0)
    d1 = _backoff_delay(1, base=1.0, cap=10.0, jitter=0)
    d2 = _backoff_delay(2, base=1.0, cap=10.0, jitter=0)
    d_high = _backoff_delay(20, base=1.0, cap=10.0, jitter=0)
    assert d0 == 1.0
    assert d1 == 2.0
    assert d2 == 4.0
    assert d_high == 10.0  # capped


def test_backoff_delay_jitter_within_range():
    for _ in range(20):
        d = _backoff_delay(3, base=1.0, cap=100.0, jitter=0.25)
        assert 6.0 <= d <= 10.0  # 8 ± 25%


def test_resolve_max_attempts_env_override(monkeypatch):
    monkeypatch.setenv("PHOTOPICKER_VISION_MAX_ATTEMPTS", "7")
    assert _resolve_max_attempts(None) == 7
    # Explicit param wins over env.
    assert _resolve_max_attempts(2) == 2


def test_resolve_max_attempts_ignores_bad_env(monkeypatch):
    monkeypatch.setenv("PHOTOPICKER_VISION_MAX_ATTEMPTS", "notint")
    assert _resolve_max_attempts(None) == 3  # falls back to default


def test_resolve_max_attempts_clamps_to_min_one():
    assert _resolve_max_attempts(0) == 1
    assert _resolve_max_attempts(-5) == 1


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
