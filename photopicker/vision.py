"""Optional Claude Vision rerank — score a photo against a user prompt.

The offline `cull` pipeline gets you tight technicals: no blur, no dupes,
sharp+well-exposed. Vision adds *taste* — "which of these actually looks like
a portfolio deck photo?" — scored by Claude Sonnet against a plain-English
prompt.

Guarded behind the `[vision]` extra so the core install stays torch-free and
dep-light. `--no-ai` and missing anthropic SDK both fall back to offline order.

The client is a Protocol so tests can inject a fake without touching the
network. `AnthropicVisionClient` is the real one.
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import logging
import os
import random
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .convert import vision_bytes

log = logging.getLogger(__name__)

VISION_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 200
DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_EDGE = 1568

# Retry policy — money code (docs/DECISIONS.md § D-005). Kept independent from
# the anthropic SDK's internal retry so we control the log surface + total budget.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_BASE = 1.0
DEFAULT_BACKOFF_CAP = 30.0
DEFAULT_BACKOFF_JITTER = 0.25  # +/- 25% jitter to avoid thundering-herd retries


class VisionRetryError(RuntimeError):
    """Raised after `max_attempts` retries failed. Carries the last exception."""

    def __init__(self, attempts: int, last_error: BaseException) -> None:
        super().__init__(
            f"Vision call failed after {attempts} attempt(s): "
            f"{type(last_error).__name__}: {last_error}"
        )
        self.attempts = attempts
        self.last_error = last_error


def _is_retryable(exc: BaseException) -> bool:
    """Classify SDK/httpx errors that are worth retrying vs terminal.

    Retryable: rate limit (429), connection errors, timeouts, transient 5xx.
    Not retryable: 4xx that isn't 429 (bad request, auth), value/type errors,
    KeyboardInterrupt / SystemExit.
    """
    if isinstance(exc, (KeyboardInterrupt, SystemExit)):
        return False
    try:
        import anthropic  # type: ignore
    except ImportError:
        anthropic = None  # type: ignore
    if anthropic is not None:
        retryable_types = tuple(
            cls for cls in (
                getattr(anthropic, "RateLimitError", None),
                getattr(anthropic, "APIConnectionError", None),
                getattr(anthropic, "APITimeoutError", None),
                getattr(anthropic, "InternalServerError", None),
                getattr(anthropic, "APIStatusError", None),
            ) if cls is not None
        )
        if retryable_types and isinstance(exc, retryable_types):
            status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
            # 4xx other than 429 are user errors — don't retry those.
            if isinstance(status, int) and 400 <= status < 500 and status != 429:
                return False
            return True
    # Network-level fallbacks (no SDK installed or a raw httpx error slipped through).
    try:
        import httpx  # type: ignore

        if isinstance(exc, (httpx.HTTPError, httpx.TimeoutException)):
            return True
    except ImportError:
        pass
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    return False


def _backoff_delay(
    attempt: int,
    base: float = DEFAULT_BACKOFF_BASE,
    cap: float = DEFAULT_BACKOFF_CAP,
    jitter: float = DEFAULT_BACKOFF_JITTER,
) -> float:
    """Exponential backoff with jitter: base * 2**attempt ± jitter, clamped to cap."""
    raw = min(base * (2 ** attempt), cap)
    if jitter:
        raw *= 1.0 + random.uniform(-jitter, jitter)
    return max(0.0, raw)


def _resolve_max_attempts(explicit: int | None) -> int:
    if explicit is not None:
        return max(1, explicit)
    env = os.environ.get("PHOTOPICKER_VISION_MAX_ATTEMPTS")
    if env:
        try:
            return max(1, int(env))
        except ValueError:
            log.warning("PHOTOPICKER_VISION_MAX_ATTEMPTS=%r not an int; using default", env)
    return DEFAULT_MAX_ATTEMPTS


def call_with_retry(
    fn: Callable[[], tuple[int, str]],
    *,
    max_attempts: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> tuple[int, str]:
    """Call `fn()` with exponential backoff on retryable failures.

    `sleep` and `on_retry` are injection points for testability. `on_retry(
    attempt_num_that_just_failed, exception, delay_before_next)` fires once per
    retry event so a progress-bar caller can surface "rate limited, sleeping
    5s" instead of a silent stall.
    """
    attempts = _resolve_max_attempts(max_attempts)
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except BaseException as exc:
            last = exc
            if not _is_retryable(exc) or attempt == attempts - 1:
                break
            delay = _backoff_delay(attempt)
            if on_retry:
                try:
                    on_retry(attempt + 1, exc, delay)
                except Exception:
                    log.exception("on_retry callback raised; continuing")
            log.warning(
                "vision call failed (attempt %d/%d): %s; sleeping %.2fs",
                attempt + 1, attempts, exc, delay,
            )
            sleep(delay)
    assert last is not None
    raise VisionRetryError(attempts=attempts, last_error=last)

SYSTEM_PROMPT = (
    "You are an expert photo curator. Given one photo and a user prompt, "
    "score 0-100 how well it matches the prompt on composition, subject "
    "clarity, lighting, and portfolio quality. "
    "Reply with ONLY a JSON object of shape "
    '{"score": <int 0-100>, "reason": "<one short sentence>"}. '
    "Do not include any other text."
)


@dataclass
class VisionScore:
    path: Path
    score: int
    reason: str


class VisionClient(Protocol):
    def score_photo(
        self, image_bytes: bytes, media_type: str, prompt: str
    ) -> tuple[int, str]:
        """Return `(0-100 score, one-line reason)` for the image against the prompt."""


class AnthropicVisionClient:
    """Real Claude Vision client. Requires `pip install photopicker[vision]`.

    Wraps every messages.create call in `call_with_retry` — LAW #7 (money
    code is sacred). Retryable failures (429, 5xx, timeouts, connection drops)
    get up to `max_attempts` exponential-backoff attempts; user errors (401,
    400 other than 429) fail fast so the batch doesn't burn cycles retrying
    a bad key.
    """

    def __init__(
        self,
        model: str = VISION_MODEL,
        max_attempts: int | None = None,
        on_retry: Callable[[int, BaseException, float], None] | None = None,
    ) -> None:
        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Claude Vision rerank needs `pip install photopicker[vision]`. "
                "Install it or pass --no-ai."
            ) from exc
        self._anthropic = anthropic
        self.model = model
        self._client = anthropic.Anthropic()
        self.max_attempts = max_attempts
        self.on_retry = on_retry

    def score_photo(
        self, image_bytes: bytes, media_type: str, prompt: str
    ) -> tuple[int, str]:
        import base64

        b64 = base64.standard_b64encode(image_bytes).decode()

        def _once() -> tuple[int, str]:
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": b64,
                                },
                            },
                            {"type": "text", "text": f"User prompt: {prompt}"},
                        ],
                    }
                ],
            )
            text = "".join(getattr(b, "text", "") for b in msg.content)
            return parse_vision_reply(text)

        return call_with_retry(
            _once, max_attempts=self.max_attempts, on_retry=self.on_retry
        )


_JSON_OBJ_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def parse_vision_reply(text: str) -> tuple[int, str]:
    """Extract `(score, reason)` from a model reply.

    Tolerant of surrounding whitespace / stray markdown fences the model
    sometimes leaks despite the system prompt. Falls back to `(0, raw text)`
    on unparseable input so a single bad reply never crashes the batch.
    """
    match = _JSON_OBJ_RE.search(text or "")
    if not match:
        return 0, (text or "").strip()[:120]
    try:
        obj = json.loads(match.group(0))
    except json.JSONDecodeError:
        return 0, (text or "").strip()[:120]
    raw_score = obj.get("score", 0)
    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))
    reason = str(obj.get("reason", "")).strip()[:200]
    return score, reason


def rerank(
    paths: Iterable[Path],
    prompt: str,
    client: VisionClient,
    top_n: int | None = None,
    max_workers: int = DEFAULT_MAX_WORKERS,
    max_edge: int = DEFAULT_MAX_EDGE,
    progress: Callable[[int, int], None] | None = None,
) -> list[VisionScore]:
    """Score every path against `prompt`, return descending by score.

    Parallelised across `max_workers` threads — each Vision call is a network
    round-trip so I/O concurrency helps even without a GIL release.
    Truncated to `top_n` when set; original order preserved among ties.
    """
    paths = list(paths)
    if not paths:
        return []

    # Precompute jpeg bytes so we don't hold GIL / re-encode from worker threads.
    from .convert import ImageUnreadable

    prepared: list[tuple[Path, bytes, str]] = []
    for p in paths:
        try:
            data, media = vision_bytes(p, max_edge=max_edge)
        except ImageUnreadable as exc:
            log.info("skipping unreadable image %s: %s", p.name, exc)
            continue
        except Exception:  # unexpected — surface but don't crash the batch
            log.exception("unexpected error preparing %s", p.name)
            continue
        prepared.append((p, data, media))

    results: list[VisionScore] = []
    done = 0
    total = len(prepared)
    if progress:
        progress(0, total)
    with cf.ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_path = {
            pool.submit(client.score_photo, data, media, prompt): path
            for path, data, media in prepared
        }
        for future in cf.as_completed(future_to_path):
            path = future_to_path[future]
            try:
                score, reason = future.result()
            except Exception as exc:
                score, reason = 0, f"error: {exc}"[:120]
            results.append(VisionScore(path=path, score=score, reason=reason))
            done += 1
            if progress:
                progress(done, total)

    results.sort(key=lambda r: r.score, reverse=True)
    if top_n is not None:
        results = results[:top_n]
    return results
