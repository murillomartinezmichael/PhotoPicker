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
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .convert import vision_bytes

VISION_MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 200
DEFAULT_MAX_WORKERS = 4
DEFAULT_MAX_EDGE = 1568

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
    """Real Claude Vision client. Requires `pip install photopicker[vision]`."""

    def __init__(self, model: str = VISION_MODEL) -> None:
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

    def score_photo(
        self, image_bytes: bytes, media_type: str, prompt: str
    ) -> tuple[int, str]:
        import base64

        b64 = base64.standard_b64encode(image_bytes).decode()
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
    prepared: list[tuple[Path, bytes, str]] = []
    for p in paths:
        try:
            data, media = vision_bytes(p, max_edge=max_edge)
        except Exception:
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
