"""Local-only web UI for photo culling — grid, keyboard, export.

Design intent: `photopicker-cull ./shoot --top 30 --serve` opens a browser tab
and Michael culls 500 → 30 in under 10 minutes with two keys (K/X). Stdlib
http.server only — no FastAPI, no build step — so the core install stays
dep-light and the UI ships offline.

Endpoints (all local, no auth — 127.0.0.1 only):
    GET  /                    HTML shell
    GET  /state               JSON session state
    GET  /photo/<idx>?w=N     JPEG thumbnail bytes, cached
    POST /decision            {"idx": N, "decision": "keep"|"reject"|"clear"}
    POST /undo                undoes last decision
    POST /reset               clears every decision
    POST /export              {"target": "/path"} — copies keepers there
    POST /shutdown            stops the server

Session state persists to `.photopicker-session.json` in the source folder so
Ctrl+C mid-cull isn't a data-loss event.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .convert import ImageUnreadable, copy_or_transcode, thumbnail_bytes
from .xmp import embed_xmp_rating, rating_for_rank

DEFAULT_PORT = 8765
SESSION_FILE = ".photopicker-session.json"
THUMB_WIDTH = 480
FOCUS_WIDTH = 1200
DEFAULT_JPG_QUALITY = 85

log = logging.getLogger(__name__)

Decision = str  # "keep" | "reject" | ""


class CullProgressBroker:
    """Thread-safe pub/sub for the initial cull's progress state.

    Producer (background cull thread) calls `update(stage, done, total)` as the
    pipeline moves. Consumers (SSE subscribers on `/progress`) block on
    `wait_for_change(last_serial)` and receive the current snapshot the moment
    it changes — no polling on the wire.

    Marking the cull done (`mark_finished`) frees every waiting consumer so the
    UI's SSE stream returns EOF and the frontend flips to the review grid.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._stage = ""
        self._done = 0
        self._total = 0
        self._serial = 0
        self._finished = False

    def update(self, stage: str, done: int, total: int) -> None:
        with self._cond:
            if (stage, done, total) == (self._stage, self._done, self._total):
                return
            self._stage = stage
            self._done = int(done)
            self._total = int(total)
            self._serial += 1
            self._cond.notify_all()

    def mark_finished(self) -> None:
        with self._cond:
            if self._finished:
                return
            self._finished = True
            self._serial += 1
            self._cond.notify_all()

    def snapshot(self) -> dict[str, Any]:
        with self._cond:
            return {
                "stage": self._stage,
                "done": self._done,
                "total": self._total,
                "finished": self._finished,
                "serial": self._serial,
            }

    def wait_for_change(self, last_serial: int, timeout: float = 15.0) -> dict[str, Any]:
        """Block until serial > last_serial, or timeout hits. Returns a snapshot."""
        with self._cond:
            if self._serial > last_serial:
                return self._snapshot_locked()
            self._cond.wait(timeout=timeout)
            return self._snapshot_locked()

    def _snapshot_locked(self) -> dict[str, Any]:
        return {
            "stage": self._stage,
            "done": self._done,
            "total": self._total,
            "finished": self._finished,
            "serial": self._serial,
        }


NULL_PROGRESS = CullProgressBroker()
NULL_PROGRESS.mark_finished()  # sentinel used when a session was hydrated (no cull to watch)


@dataclass
class Candidate:
    idx: int
    path: str
    filename: str
    score: float = 0.0
    ai_score: int | None = None
    ai_reason: str = ""
    decision: Decision = ""
    capture_time: str | None = None
    rejected_reason: str = ""  # "" when the pipeline kept it as a keeper


@dataclass
class Session:
    source_folder: str
    candidates: list[Candidate]
    prompt: str = ""
    history: list[int] = field(default_factory=list)  # idxs of decisions in order made
    reject_summary: dict[str, int] = field(default_factory=dict)
    input_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_folder": self.source_folder,
            "prompt": self.prompt,
            "input_count": self.input_count,
            "reject_summary": self.reject_summary,
            "candidates": [asdict(c) for c in self.candidates],
            "history": list(self.history),
            "counts": self.counts(),
        }

    def counts(self) -> dict[str, int]:
        keeps = sum(1 for c in self.candidates if c.decision == "keep")
        rejects = sum(1 for c in self.candidates if c.decision == "reject")
        undecided = sum(1 for c in self.candidates if not c.decision)
        return {"total": len(self.candidates), "keep": keeps, "reject": rejects, "undecided": undecided}


class SessionStore:
    """Thread-safe wrapper around a Session on disk."""

    def __init__(self, session: Session, session_path: Path) -> None:
        self._lock = threading.RLock()
        self.session = session
        self.session_path = session_path
        self._save()

    def _save(self) -> None:
        try:
            self.session_path.write_text(json.dumps(self.session.to_dict(), indent=2))
        except OSError as exc:  # non-fatal — UI keeps working, restart won't recover
            log.warning("Could not persist session to %s: %s", self.session_path, exc)

    def get(self) -> Session:
        with self._lock:
            return self.session

    def decide(self, idx: int, decision: Decision) -> None:
        with self._lock:
            if not (0 <= idx < len(self.session.candidates)):
                raise IndexError(idx)
            if decision not in ("keep", "reject", ""):
                raise ValueError(decision)
            self.session.candidates[idx].decision = decision
            self.session.history.append(idx)
            self._save()

    def undo(self) -> int | None:
        with self._lock:
            if not self.session.history:
                return None
            idx = self.session.history.pop()
            self.session.candidates[idx].decision = ""
            self._save()
            return idx

    def reset(self) -> None:
        with self._lock:
            for c in self.session.candidates:
                c.decision = ""
            self.session.history.clear()
            self._save()

    def hydrate(self, new_session: Session) -> None:
        """Swap the underlying session — used when the cull thread finishes
        and the initially-empty store gets the real candidate set."""
        with self._lock:
            self.session = new_session
            self._save()

    def keepers(self) -> list[Path]:
        with self._lock:
            return [Path(c.path) for c in self.session.candidates if c.decision == "keep"]

    def undecided_keepers(self) -> list[Path]:
        """Keepers + candidates still undecided (treated as keepers on export)."""
        with self._lock:
            return [
                Path(c.path)
                for c in self.session.candidates
                if c.decision in ("keep", "")
            ]


def _override_stats(session: Session) -> dict[str, Any] | None:
    """The honest accuracy metric: how often the human reverses pipeline picks.

    Picks = candidates the pipeline surfaced as keepers (no `rejected_reason`).
    An override is a pick the human rejected; undecided counts as kept — that
    is exactly how export treats it. Rescues (pipeline rejects flipped to keep)
    are counted separately. Returns None when the session has no picks.
    """
    picks = [c for c in session.candidates if not c.rejected_reason]
    if not picks:
        return None
    overridden = sum(1 for c in picks if c.decision == "reject")
    kept = len(picks) - overridden
    rate = overridden / len(picks)
    rescued = sum(
        1 for c in session.candidates if c.rejected_reason and c.decision == "keep"
    )
    line = f"kept {kept}/{len(picks)} picks — {round(rate * 100)}% override"
    if rescued:
        line += f" · rescued {rescued} pipeline reject{'s' if rescued != 1 else ''}"
    return {
        "picks": len(picks),
        "kept": kept,
        "overridden": overridden,
        "rate": round(rate, 4),
        "rescued": rescued,
        "line": line,
    }


def _build_export_manifest(
    session: Session,
    src_to_dest: dict[Path, Path],
    target_dir: Path,
) -> dict[str, Any]:
    """Emit a JSON manifest keyed by exported filename.

    Fields per pick: rank (order of export), source_filename, output_filename,
    score, ai_score, ai_reason, capture_time, decision.
    """
    from datetime import datetime, timezone

    exported_paths = list(src_to_dest.values())
    by_source = {str(src): dest for src, dest in src_to_dest.items()}
    picks = []
    rank = 0
    for c in session.candidates:
        dest = by_source.get(c.path)
        if dest is None:
            continue
        rank += 1
        entry = {
            "rank": rank,
            "source_filename": c.filename,
            "output_filename": dest.name,
            "score": round(c.score, 4),
            "capture_time": c.capture_time,
            "decision": c.decision or "undecided",
        }
        if c.ai_score is not None:
            entry["ai_score"] = c.ai_score
            entry["ai_reason"] = c.ai_reason
        picks.append(entry)
    return {
        "source_folder": session.source_folder,
        "prompt": session.prompt,
        "target": str(target_dir),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "reject_summary": session.reject_summary,
        "input_count": session.input_count,
        "exported_count": len(exported_paths),
        "override": _override_stats(session),
        "picks": picks,
    }


def _load_session_from_disk(session_path: Path, candidates: list[Candidate]) -> list[Candidate]:
    """Restore prior decisions from `.photopicker-session.json` if the candidate
    set matches by path. Returns the (possibly-updated) candidates list."""
    if not session_path.exists():
        return candidates
    try:
        prior = json.loads(session_path.read_text())
    except (OSError, json.JSONDecodeError):
        return candidates
    by_path = {c["path"]: c for c in prior.get("candidates", [])}
    for cand in candidates:
        prior_c = by_path.get(cand.path)
        if prior_c is not None:
            cand.decision = prior_c.get("decision", "") or ""
    return candidates


def build_session(
    source_folder: Path,
    keepers: list[Path],
    scores: dict[Path, float] | None = None,
    reject_summary: dict[str, int] | None = None,
    input_count: int = 0,
    prompt: str = "",
    ai_scores: dict[Path, tuple[int, str]] | None = None,
    include_rejects: dict[str, list[Path]] | None = None,
) -> Session:
    """Wrap a cull result in an editable Session for the web UI.

    When `include_rejects` is provided, quality-gate rejects (blurry / dupes /
    tiny / unreadable) are added to the candidate list *after* the keepers,
    with `rejected_reason` set. The UI hides them behind a filter chip so you
    can rescue false positives without them cluttering the default grid.
    """
    from .exif import get_capture_time

    scores = scores or {}
    ai_scores = ai_scores or {}
    candidates: list[Candidate] = []
    for i, p in enumerate(keepers):
        ai = ai_scores.get(p)
        capture = get_capture_time(p)
        candidates.append(
            Candidate(
                idx=i,
                path=str(p),
                filename=p.name,
                score=float(scores.get(p, 0.0)),
                ai_score=ai[0] if ai else None,
                ai_reason=ai[1] if ai else "",
                capture_time=capture.isoformat() if capture else None,
            )
        )
    if include_rejects:
        seen = {c.path for c in candidates}
        for reason, reject_paths in include_rejects.items():
            for p in reject_paths:
                if str(p) in seen or reason == "unreadable":
                    continue
                seen.add(str(p))
                try:
                    capture = get_capture_time(p)
                except Exception:
                    capture = None
                candidates.append(
                    Candidate(
                        idx=len(candidates),
                        path=str(p),
                        filename=p.name,
                        score=0.0,
                        capture_time=capture.isoformat() if capture else None,
                        rejected_reason=reason,
                    )
                )
    session_path = source_folder / SESSION_FILE
    candidates = _load_session_from_disk(session_path, candidates)
    return Session(
        source_folder=str(source_folder),
        candidates=candidates,
        prompt=prompt,
        reject_summary=dict(reject_summary or {}),
        input_count=input_count,
    )


# --- HTTP layer --------------------------------------------------------------


class _ThumbCache:
    def __init__(self, max_entries: int = 200) -> None:
        self._lock = threading.Lock()
        self._cache: dict[tuple[str, int], bytes] = {}
        self._max = max_entries

    def get_or_render(self, path: Path, width: int) -> bytes:
        key = (str(path), width)
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                return hit
        data = thumbnail_bytes(path, width=width, fmt="jpg", quality=DEFAULT_JPG_QUALITY)
        with self._lock:
            if len(self._cache) >= self._max:
                # Cheap FIFO — first inserted key drops.
                first = next(iter(self._cache))
                self._cache.pop(first, None)
            self._cache[key] = data
        return data


def make_handler(
    store: SessionStore,
    thumb_cache: _ThumbCache,
    shutdown_event: threading.Event,
    progress: CullProgressBroker | None = None,
) -> type[BaseHTTPRequestHandler]:
    progress = progress or NULL_PROGRESS

    class Handler(BaseHTTPRequestHandler):
        # Silence per-request stderr — the server logs to `log` explicitly.
        def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
            log.debug("%s - %s", self.address_string(), format % args)

        # ---- routing ----
        def do_GET(self) -> None:  # noqa: N802
            try:
                if self.path == "/" or self.path.startswith("/?"):
                    self._send_html()
                elif self.path == "/state":
                    self._send_json(store.get().to_dict())
                elif self.path == "/progress":
                    self._send_json(progress.snapshot())
                elif self.path == "/progress/stream":
                    self._stream_progress()
                elif self.path.startswith("/photo/"):
                    self._handle_photo()
                elif self.path == "/health":
                    self._send_json({"status": "ok"})
                else:
                    self._send_text(HTTPStatus.NOT_FOUND, "not found")
            except Exception:
                log.exception("GET %s failed", self.path)
                self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "server error")

        def do_POST(self) -> None:  # noqa: N802
            try:
                if self.path == "/decision":
                    self._handle_decision()
                elif self.path == "/undo":
                    idx = store.undo()
                    self._send_json({"undone_idx": idx, "state": store.get().to_dict()})
                elif self.path == "/reset":
                    store.reset()
                    self._send_json({"state": store.get().to_dict()})
                elif self.path == "/export":
                    self._handle_export()
                elif self.path == "/shutdown":
                    self._send_json({"stopping": True})
                    shutdown_event.set()
                else:
                    self._send_text(HTTPStatus.NOT_FOUND, "not found")
            except Exception:
                log.exception("POST %s failed", self.path)
                self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "server error")

        # ---- helpers ----
        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0") or 0)
            if not length:
                return {}
            raw = self.rfile.read(length)
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {}

        def _send_text(self, status: HTTPStatus, body: str, ctype: str = "text/plain") -> None:
            data = body.encode("utf-8")
            self.send_response(int(status))
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            self._send_text(status, json.dumps(payload), ctype="application/json")

        def _send_html(self) -> None:
            self._send_text(HTTPStatus.OK, INDEX_HTML, ctype="text/html")

        def _send_bytes(self, data: bytes, ctype: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(data)

        def _stream_progress(self) -> None:
            """SSE stream — one event per broker change until finished.

            Bounded by ~5 min wall-clock so a browser tab that forgets to
            close doesn't hold a thread forever. The frontend reconnects if
            EventSource fires an error before the finished marker arrives.
            """
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last_serial = -1
            wall_deadline = time.time() + 300  # 5 minute upper bound
            try:
                while time.time() < wall_deadline:
                    snap = progress.wait_for_change(last_serial, timeout=15.0)
                    last_serial = snap["serial"]
                    payload = json.dumps(snap)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                    self.wfile.flush()
                    if snap["finished"]:
                        break
            except (BrokenPipeError, ConnectionResetError):
                # Browser closed the tab; that's the happy path.
                return

        # ---- handlers ----
        def _handle_photo(self) -> None:
            # /photo/<idx>?w=N
            _, _, rest = self.path.partition("/photo/")
            idx_str, _, qs = rest.partition("?")
            try:
                idx = int(idx_str)
            except ValueError:
                self._send_text(HTTPStatus.BAD_REQUEST, "bad idx")
                return
            width = THUMB_WIDTH
            if qs:
                for pair in qs.split("&"):
                    k, _, v = pair.partition("=")
                    if k == "w":
                        try:
                            width = max(64, min(2400, int(v)))
                        except ValueError:
                            pass
            session = store.get()
            if not (0 <= idx < len(session.candidates)):
                self._send_text(HTTPStatus.NOT_FOUND, "no such photo")
                return
            path = Path(session.candidates[idx].path)
            try:
                data = thumb_cache.get_or_render(path, width)
            except ImageUnreadable as exc:
                # Corrupt or unreadable source — return 500 with a real
                # message so the operator sees "file broken" not "server error".
                log.warning("thumbnail unreadable: %s", exc)
                self._send_text(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    f"could not read {path.name}",
                )
                return
            except Exception:
                log.exception("thumbnail render failed for %s", path)
                self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "thumbnail failed")
                return
            self._send_bytes(data, "image/jpeg")

        def _handle_decision(self) -> None:
            body = self._read_json()
            try:
                idx = int(body.get("idx"))
            except (TypeError, ValueError):
                self._send_text(HTTPStatus.BAD_REQUEST, "bad idx")
                return
            decision = str(body.get("decision", ""))
            try:
                store.decide(idx, decision)
            except IndexError:
                self._send_text(HTTPStatus.NOT_FOUND, "no such photo")
                return
            except ValueError:
                self._send_text(HTTPStatus.BAD_REQUEST, "bad decision")
                return
            self._send_json({"ok": True, "state": store.get().to_dict()})

        def _handle_export(self) -> None:
            body = self._read_json()
            target = body.get("target", "")
            if not target:
                self._send_text(HTTPStatus.BAD_REQUEST, "target required")
                return
            include_undecided = bool(body.get("include_undecided", False))
            convert_heic = bool(body.get("convert_heic", True))
            write_manifest = bool(body.get("write_manifest", False))
            embed_xmp = bool(body.get("xmp", False))
            target_dir = Path(str(target)).expanduser()
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self._send_text(HTTPStatus.BAD_REQUEST, f"cannot create target: {exc}")
                return
            paths = (
                store.undecided_keepers() if include_undecided else store.keepers()
            )
            if not paths:
                self._send_json({"exported": 0, "target": str(target_dir), "note": "nothing to export"})
                return
            src_to_dest: dict[Path, Path] = {}
            rated = 0
            for rank, src in enumerate(paths, start=1):
                try:
                    dest = copy_or_transcode(src, target_dir, convert_heic=convert_heic)
                    src_to_dest[src] = dest
                    if embed_xmp and embed_xmp_rating(
                        dest, rating_for_rank(rank, len(paths))
                    ):
                        rated += 1
                except Exception:
                    log.exception("export failed for %s", src)
            written = [p.name for p in src_to_dest.values()]
            payload: dict[str, Any] = {
                "exported": len(written),
                "target": str(target_dir),
                "files": written,
            }
            if embed_xmp:
                payload["xmp_embedded"] = rated
            override = _override_stats(store.get())
            if override is not None:
                payload["override"] = override
            if write_manifest and src_to_dest:
                manifest = _build_export_manifest(store.get(), src_to_dest, target_dir)
                manifest_path = target_dir / "manifest.json"
                try:
                    manifest_path.write_text(json.dumps(manifest, indent=2))
                    payload["manifest_written"] = manifest_path.name
                except OSError as exc:
                    log.warning("manifest write failed: %s", exc)
                    payload["manifest_error"] = str(exc)
            self._send_json(payload)

    return Handler


PORT_FALLBACK_TRIES = 10


def _bind_with_fallback(
    handler_cls: type[BaseHTTPRequestHandler],
    host: str,
    port: int,
    tries: int = PORT_FALLBACK_TRIES,
) -> tuple[ThreadingHTTPServer, int]:
    """Try `port`, then `port+1..port+tries`. Return `(httpd, actual_port)`.

    Raises `OSError` only when EVERY tried port is taken. This is the operator
    UX we want: "8765 is busy, running on 8766 instead" beats a hard fail.
    """
    last_exc: OSError | None = None
    for offset in range(tries + 1):
        candidate = port + offset
        try:
            return ThreadingHTTPServer((host, candidate), handler_cls), candidate
        except OSError as exc:
            last_exc = exc
            log.info("port %d unavailable (%s); trying next", candidate, exc)
    assert last_exc is not None
    raise OSError(
        f"Could not bind on {host}:{port}..{port + tries} — every port in the "
        f"fallback range was taken. Pass --port with an unused port."
    ) from last_exc


def serve(
    store: SessionStore,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    host: str = "127.0.0.1",
    port_fallback_tries: int = PORT_FALLBACK_TRIES,
    progress: CullProgressBroker | None = None,
) -> None:
    """Blocking. Runs until POST /shutdown or Ctrl+C.

    Only binds to `127.0.0.1` — this is a local review UI, not a shared service.
    If `port` is taken, tries `port+1..port+port_fallback_tries` before failing.
    When `progress` is given, `/progress/stream` serves an SSE feed of cull
    pipeline updates; the UI hangs on that until finish, then renders the grid.
    """
    thumb_cache = _ThumbCache()
    shutdown_event = threading.Event()
    handler_cls = make_handler(store, thumb_cache, shutdown_event, progress=progress)
    httpd, actual_port = _bind_with_fallback(
        handler_cls, host, port, tries=port_fallback_tries
    )

    watcher = threading.Thread(
        target=lambda: (shutdown_event.wait(), httpd.shutdown()),
        daemon=True,
    )
    watcher.start()

    url = f"http://{host}:{actual_port}/"
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    log.info("photopicker web UI at %s", url)
    if actual_port != port:
        print(f"photopicker: port {port} was busy; landed on {actual_port}")
    print(f"photopicker cull UI -> {url}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        shutdown_event.set()
    finally:
        httpd.server_close()


# --- HTML shell --------------------------------------------------------------
#
# Kept as a single inlined string on purpose: the UI ships with the wheel, no
# static-files decision, no build step. Style follows the repo visual standard
# (monospace, LEDs, scanlines, ambient motion).

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>photopicker · cull</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {
    --bg: #07090c;
    --panel: #0e1218;
    --line: #1c2530;
    --ink: #d8e2ee;
    --muted: #6b7a90;
    --cyan: #4de5ff;
    --magenta: #ff4dd8;
    --keep: #29d17a;
    --reject: #ff4d6a;
    --amber: #ffcc4d;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; }
  body {
    background: var(--bg);
    color: var(--ink);
    font-family: 'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace;
    font-size: 13px;
    overflow: hidden;
    position: relative;
  }
  body::before {
    /* Scanline overlay */
    content: '';
    position: fixed; inset: 0;
    background: repeating-linear-gradient(
      to bottom,
      rgba(255,255,255,0.02) 0 1px,
      transparent 1px 3px
    );
    pointer-events: none;
    z-index: 100;
  }
  body::after {
    /* Ambient drift glow */
    content: '';
    position: fixed; inset: -20% -20% -20% -20%;
    background: radial-gradient(circle at 20% 15%, rgba(77,229,255,0.06), transparent 40%),
                radial-gradient(circle at 80% 80%, rgba(255,77,216,0.05), transparent 40%);
    pointer-events: none;
    z-index: 0;
    animation: drift 40s linear infinite;
  }
  @keyframes drift {
    0%   { transform: translate(0,0); }
    50%  { transform: translate(-2%, 1%); }
    100% { transform: translate(0,0); }
  }
  header {
    position: relative; z-index: 2;
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 16px;
    background: linear-gradient(180deg, var(--panel), transparent);
    border-bottom: 1px solid var(--line);
  }
  header .brand {
    display: flex; align-items: center; gap: 12px;
    font-weight: 600; letter-spacing: 0.06em;
  }
  header .brand .dot {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--cyan);
    box-shadow: 0 0 12px var(--cyan);
    animation: pulse 1.6s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,100% { opacity: 1; }
    50% { opacity: 0.4; }
  }
  header .brand h1 { font-size: 13px; margin: 0; text-transform: uppercase; }
  header .brand small { color: var(--muted); }
  .leds { display: flex; align-items: center; gap: 10px; }
  .led {
    display: flex; align-items: center; gap: 6px;
    padding: 4px 10px;
    border: 1px solid var(--line);
    background: rgba(255,255,255,0.02);
    border-radius: 2px;
    font-size: 11px;
    letter-spacing: 0.05em;
  }
  .led .bulb {
    width: 8px; height: 8px; border-radius: 50%;
    background: var(--muted);
    box-shadow: 0 0 6px currentColor;
  }
  .led.keep .bulb { background: var(--keep); box-shadow: 0 0 8px var(--keep); }
  .led.reject .bulb { background: var(--reject); box-shadow: 0 0 8px var(--reject); }
  .led.undecided .bulb { background: var(--amber); box-shadow: 0 0 8px var(--amber); }
  .led.total .bulb { background: var(--cyan); box-shadow: 0 0 8px var(--cyan); }
  .led .n { font-weight: 700; color: var(--ink); }
  .led .label { color: var(--muted); text-transform: uppercase; }
  header .actions button {
    background: transparent; color: var(--ink);
    border: 1px solid var(--line);
    padding: 6px 10px;
    font: inherit; cursor: pointer;
    letter-spacing: 0.05em;
    text-transform: uppercase;
    transition: all 120ms ease;
  }
  header .actions button:hover {
    border-color: var(--cyan);
    color: var(--cyan);
    box-shadow: 0 0 8px rgba(77,229,255,0.3);
  }
  main {
    position: relative; z-index: 1;
    height: calc(100vh - 46px - 30px - 40px);
    overflow-y: auto;
  }
  .grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 8px;
    padding: 16px;
  }
  .card {
    position: relative;
    background: var(--panel);
    border: 1px solid var(--line);
    aspect-ratio: 1 / 1;
    overflow: hidden;
    cursor: pointer;
    transition: transform 100ms ease, box-shadow 100ms ease;
  }
  .card img {
    width: 100%; height: 100%;
    object-fit: cover;
    display: block;
    opacity: 0; transition: opacity 200ms ease;
  }
  .card img.loaded { opacity: 1; }
  .card .meta {
    position: absolute; bottom: 0; left: 0; right: 0;
    padding: 4px 6px;
    background: linear-gradient(0deg, rgba(0,0,0,0.75), transparent);
    display: flex; justify-content: space-between;
    font-size: 10px;
    color: var(--muted);
    letter-spacing: 0.05em;
  }
  .card .idx {
    position: absolute; top: 4px; left: 4px;
    background: rgba(0,0,0,0.6);
    padding: 2px 6px;
    font-size: 10px; color: var(--muted);
    border: 1px solid var(--line);
    letter-spacing: 0.06em;
  }
  .card.focused {
    box-shadow: 0 0 0 2px var(--cyan), 0 0 16px rgba(77,229,255,0.4);
    z-index: 3;
  }
  .card.keep {
    box-shadow: 0 0 0 2px var(--keep) inset;
  }
  .card.keep::after {
    content: 'KEEP';
    position: absolute; top: 4px; right: 4px;
    background: var(--keep); color: #041;
    padding: 2px 6px; font-size: 10px; font-weight: 700;
    letter-spacing: 0.1em;
  }
  .card.reject {
    box-shadow: 0 0 0 2px var(--reject) inset;
  }
  .card.reject img { filter: grayscale(1) brightness(0.5); }
  .card.reject::after {
    content: 'REJECT';
    position: absolute; top: 4px; right: 4px;
    background: var(--reject); color: #400;
    padding: 2px 6px; font-size: 10px; font-weight: 700;
    letter-spacing: 0.1em;
  }
  footer {
    position: fixed; bottom: 0; left: 0; right: 0;
    height: 30px;
    background: var(--panel);
    border-top: 1px solid var(--line);
    display: flex; align-items: center; justify-content: space-between;
    padding: 0 16px;
    z-index: 2;
    font-size: 11px; color: var(--muted);
  }
  footer .keys kbd {
    background: rgba(255,255,255,0.06);
    border: 1px solid var(--line);
    padding: 1px 5px;
    margin: 0 2px;
    font-family: inherit; font-size: 10px;
    color: var(--ink);
  }
  #focus-view {
    position: fixed; inset: 0;
    background: rgba(4,6,10,0.94);
    display: none;
    align-items: center; justify-content: center;
    z-index: 50;
    padding: 40px;
    flex-direction: column;
  }
  #focus-view.on { display: flex; }
  #focus-view img {
    max-width: 100%; max-height: calc(100vh - 160px);
    object-fit: contain;
    border: 1px solid var(--line);
    box-shadow: 0 0 20px rgba(77,229,255,0.15);
  }
  #focus-view .focus-meta {
    margin-top: 14px;
    display: flex; gap: 18px; align-items: center;
    font-size: 12px; color: var(--muted);
    letter-spacing: 0.05em;
  }
  #focus-view .focus-meta strong { color: var(--ink); }
  #focus-view .focus-meta .prompt-line { color: var(--muted); }
  #focus-view .focus-stats {
    margin-top: 10px;
    display: flex; gap: 16px; align-items: baseline; flex-wrap: wrap;
    padding: 8px 14px;
    background: var(--panel);
    border: 1px solid var(--line);
    font-size: 12px; color: var(--muted);
    letter-spacing: 0.05em;
    max-width: min(90vw, 760px);
  }
  #focus-view .focus-stats .val { color: var(--ink); font-weight: 700; }
  #focus-view .focus-stats .pct { color: var(--cyan); }
  #focus-view .focus-stats .reason { color: var(--muted); }
  #focus-view .focus-stats .culled { color: var(--reject); }
  #focus-view .close-hint { position: absolute; top: 12px; right: 16px; color: var(--muted); font-size: 11px; }
  #export-dialog, #help-dialog {
    position: fixed; inset: 0;
    background: rgba(4,6,10,0.88);
    display: none;
    align-items: center; justify-content: center;
    z-index: 60;
  }
  #export-dialog.on, #help-dialog.on { display: flex; }
  #export-dialog .box, #help-dialog .box {
    background: var(--panel);
    border: 1px solid var(--cyan);
    box-shadow: 0 0 24px rgba(77,229,255,0.2);
    padding: 22px 24px;
    min-width: 420px;
    max-width: 640px;
  }
  #export-dialog h2, #help-dialog h2 {
    margin: 0 0 12px 0;
    font-size: 13px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--cyan);
  }
  #export-dialog input[type="text"] {
    width: 100%;
    background: var(--bg);
    border: 1px solid var(--line);
    color: var(--ink);
    padding: 8px 10px;
    font: inherit;
    margin-bottom: 12px;
  }
  #export-dialog label {
    display: flex; align-items: center; gap: 6px;
    font-size: 11px; color: var(--muted);
    margin: 6px 0;
  }
  #export-dialog .actions, #help-dialog .actions {
    display: flex; gap: 8px; justify-content: flex-end;
    margin-top: 14px;
  }
  #export-dialog button, #help-dialog button {
    background: transparent; color: var(--ink);
    border: 1px solid var(--line);
    padding: 6px 12px;
    font: inherit; cursor: pointer;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  #export-dialog button.primary { border-color: var(--cyan); color: var(--cyan); }
  #export-dialog button.primary:hover { box-shadow: 0 0 8px rgba(77,229,255,0.35); }
  #export-result {
    margin-top: 12px; padding: 8px 10px;
    border: 1px solid var(--line); background: var(--bg);
    color: var(--keep); font-size: 12px; display: none;
  }
  #export-result.err { color: var(--reject); border-color: var(--reject); }
  #help-dialog dl { margin: 0; }
  #help-dialog dt { color: var(--cyan); margin-top: 8px; font-weight: 700; }
  #help-dialog dd { margin: 0 0 4px 0; color: var(--muted); }
  .filters {
    display: flex; gap: 6px;
    padding: 8px 16px 0 16px;
    position: relative; z-index: 2;
  }
  .filters .chip {
    background: transparent;
    color: var(--muted);
    border: 1px solid var(--line);
    padding: 4px 10px;
    font: inherit; font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    cursor: pointer;
    transition: all 100ms ease;
  }
  .filters .chip:hover { color: var(--ink); border-color: var(--ink); }
  .filters .chip.on {
    color: var(--cyan);
    border-color: var(--cyan);
    box-shadow: 0 0 6px rgba(77,229,255,0.35);
  }
  .filters .chip .count {
    display: inline-block; margin-left: 6px;
    color: var(--muted); opacity: 0.7;
  }
  .filters .chip.on .count { color: var(--cyan); opacity: 1; }
  .filters .spacer { flex: 1; }
  .filters .sort {
    color: var(--muted);
    background: transparent;
    border: 1px solid var(--line);
    padding: 3px 8px; font: inherit; font-size: 11px;
    letter-spacing: 0.06em; text-transform: uppercase;
  }
  .card.rejected-input {
    box-shadow: 0 0 0 1px #4a3040 inset;
    opacity: 0.62;
  }
  .card.rejected-input .idx { border-color: #4a3040; }
  .card .rej-badge {
    position: absolute; top: 4px; right: 4px;
    background: #4a3040; color: #ffb0c8;
    padding: 2px 6px; font-size: 9px;
    letter-spacing: 0.1em; text-transform: uppercase;
  }
  .card .cap-time {
    position: absolute; top: 4px; right: 4px;
    background: rgba(0,0,0,0.55); color: var(--muted);
    padding: 2px 6px; font-size: 9px;
    letter-spacing: 0.05em;
    border: 1px solid var(--line);
  }
  .card .idx + .cap-time { top: 26px; }
  .card.hidden-by-filter { display: none; }
  #toast {
    position: fixed;
    bottom: 44px; left: 50%; transform: translateX(-50%);
    background: var(--panel);
    border: 1px solid var(--cyan);
    color: var(--ink);
    padding: 8px 14px;
    font-size: 12px;
    letter-spacing: 0.05em;
    box-shadow: 0 0 14px rgba(77,229,255,0.35);
    opacity: 0;
    transition: opacity 200ms ease;
    pointer-events: none;
    z-index: 200;
  }
  #toast.on { opacity: 1; }

  #progress-screen {
    position: fixed; inset: 0;
    background: var(--bg);
    display: none;
    align-items: center; justify-content: center;
    flex-direction: column;
    z-index: 300;
    padding: 40px;
  }
  #progress-screen.on { display: flex; }
  #progress-screen h2 {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: var(--muted);
    margin: 0 0 8px 0;
  }
  #progress-screen .stage {
    font-size: 20px;
    color: var(--cyan);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 20px;
    text-shadow: 0 0 12px rgba(77,229,255,0.6);
  }
  #progress-screen .bar {
    width: 380px; height: 6px;
    background: var(--panel);
    border: 1px solid var(--line);
    position: relative;
    overflow: hidden;
    margin-bottom: 8px;
  }
  #progress-screen .bar .fill {
    position: absolute; top: 0; left: 0; bottom: 0;
    background: linear-gradient(90deg, var(--cyan), var(--magenta));
    box-shadow: 0 0 12px rgba(77,229,255,0.6);
    transition: width 220ms ease;
  }
  #progress-screen .bar .fill::after {
    content: ''; position: absolute; top: 0; right: 0; bottom: 0; width: 2px;
    background: rgba(255,255,255,0.7);
  }
  #progress-screen .counts {
    color: var(--muted);
    font-size: 12px;
    letter-spacing: 0.08em;
  }
  #progress-screen .marquee {
    margin-top: 24px;
    color: var(--muted);
    font-size: 11px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    opacity: 0.7;
  }
</style>
</head>
<body>
<header>
  <div class="brand">
    <span class="dot"></span>
    <h1>photopicker · cull</h1>
    <small id="src"></small>
  </div>
  <div class="leds" id="leds"></div>
  <div class="actions">
    <button id="btn-undo" title="Undo last (U)">Undo</button>
    <button id="btn-export" title="Export keepers (E)">Export</button>
    <button id="btn-help" title="Help (?)">?</button>
  </div>
</header>
<div class="filters" id="filters">
  <button class="chip on" data-filter="all">All <span class="count" id="fc-all">0</span></button>
  <button class="chip" data-filter="undecided">Undecided <span class="count" id="fc-undecided">0</span></button>
  <button class="chip" data-filter="keep">Keepers <span class="count" id="fc-keep">0</span></button>
  <button class="chip" data-filter="reject">Rejected <span class="count" id="fc-reject">0</span></button>
  <button class="chip" data-filter="rejected-input" id="chip-rejected-input" style="display:none">Pipeline rejects <span class="count" id="fc-rejected-input">0</span></button>
  <div class="spacer"></div>
  <select class="sort" id="sort-select" title="Sort order">
    <option value="score">Sort: score</option>
    <option value="capture-time">Sort: capture time</option>
    <option value="name">Sort: filename</option>
  </select>
</div>
<main>
  <div class="grid" id="grid"></div>
</main>
<footer>
  <div class="keys">
    <kbd>K</kbd> keep · <kbd>X</kbd> reject · <kbd>U</kbd> undo · <kbd>←</kbd>/<kbd>→</kbd> nav · <kbd>Enter</kbd> focus · <kbd>F</kbd> filter · <kbd>E</kbd> export · <kbd>?</kbd> help
  </div>
  <div id="pos"></div>
</footer>

<div id="focus-view">
  <div class="close-hint">Enter or Esc to close</div>
  <img id="focus-img" alt="">
  <div class="focus-meta">
    <span><strong id="focus-name"></strong></span>
    <span id="focus-capture" class="prompt-line"></span>
  </div>
  <div class="focus-stats" id="focus-stats" aria-label="photo score details">
    <span id="focus-quality">quality <span class="val" id="focus-score"></span> <span class="pct" id="focus-pct"></span></span>
    <span id="focus-ai" style="display:none">ai <span class="val" id="focus-ai-score"></span></span>
    <span id="focus-ai-reason" class="reason"></span>
    <span id="focus-culled" class="culled" style="display:none">culled: <span id="focus-reject-reason"></span></span>
  </div>
</div>

<div id="export-dialog">
  <div class="box">
    <h2>Export keepers</h2>
    <div style="color: var(--muted); font-size: 11px; margin-bottom: 8px;">
      Copies to a folder. HEIC transcoded to JPG by default. Originals untouched.
    </div>
    <input type="text" id="export-target" placeholder="/absolute/path/to/output" autocomplete="off">
    <label><input type="checkbox" id="export-undecided"> Include undecided (treat un-marked as keepers)</label>
    <label><input type="checkbox" id="export-no-convert"> Keep HEIC as HEIC (no transcode)</label>
    <label><input type="checkbox" id="export-manifest" checked> Write manifest.json alongside exports</label>
    <label><input type="checkbox" id="export-xmp"> Embed XMP star ratings into JPEG copies (Lightroom-readable)</label>
    <div id="export-result"></div>
    <div class="actions">
      <button id="export-cancel">Cancel</button>
      <button id="export-run" class="primary">Copy keepers</button>
    </div>
  </div>
</div>

<div id="help-dialog">
  <div class="box">
    <h2>Keyboard</h2>
    <dl>
      <dt>K</dt><dd>Keep the focused photo, advance to next undecided</dd>
      <dt>X</dt><dd>Reject the focused photo, advance to next undecided</dd>
      <dt>U</dt><dd>Undo the last decision</dd>
      <dt>← / →</dt><dd>Move focus without deciding</dd>
      <dt>↑ / ↓</dt><dd>Jump 4 rows</dd>
      <dt>Enter</dt><dd>Toggle full-size focus view</dd>
      <dt>F</dt><dd>Cycle filter (All → Undecided → Keepers → Rejected → Pipeline rejects)</dd>
      <dt>E</dt><dd>Open export dialog</dd>
      <dt>Esc</dt><dd>Close dialogs / focus view</dd>
      <dt>?</dt><dd>This help</dd>
    </dl>
    <div class="actions"><button id="help-close">Close</button></div>
  </div>
</div>

<div id="toast"></div>

<div id="progress-screen">
  <h2>photopicker · cull in progress</h2>
  <div class="stage" id="prog-stage">starting</div>
  <div class="bar"><div class="fill" id="prog-fill" style="width: 0%"></div></div>
  <div class="counts" id="prog-counts">0 / 0</div>
  <div class="marquee">no photos will be moved · originals never touched</div>
</div>

<script>
'use strict';
const $ = (id) => document.getElementById(id);
const state = { session: null, focus: 0, filter: 'all', sort: 'score' };

function formatCaptureTime(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d)) return iso.slice(0, 10);
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function visibleCandidates() {
  const cs = state.session ? state.session.candidates : [];
  const filtered = cs.filter((c) => {
    if (state.filter === 'all') return !c.rejected_reason;
    if (state.filter === 'rejected-input') return !!c.rejected_reason;
    if (state.filter === 'undecided') return !c.rejected_reason && !c.decision;
    if (state.filter === 'keep') return c.decision === 'keep';
    if (state.filter === 'reject') return c.decision === 'reject';
    return true;
  });
  if (state.sort === 'name') {
    filtered.sort((a, b) => a.filename.localeCompare(b.filename));
  } else if (state.sort === 'capture-time') {
    filtered.sort((a, b) => {
      const aa = a.capture_time || 'zzz';
      const bb = b.capture_time || 'zzz';
      return aa.localeCompare(bb);
    });
  } else {
    filtered.sort((a, b) => (b.score || 0) - (a.score || 0));
  }
  return filtered;
}

function updateFilterCounts() {
  const cs = state.session ? state.session.candidates : [];
  const nonRej = cs.filter((c) => !c.rejected_reason);
  const rejInput = cs.filter((c) => c.rejected_reason);
  $('fc-all').textContent = nonRej.length;
  $('fc-undecided').textContent = nonRej.filter((c) => !c.decision).length;
  $('fc-keep').textContent = nonRej.filter((c) => c.decision === 'keep').length;
  $('fc-reject').textContent = nonRej.filter((c) => c.decision === 'reject').length;
  $('fc-rejected-input').textContent = rejInput.length;
  $('chip-rejected-input').style.display = rejInput.length ? '' : 'none';
}

async function fetchState() {
  const r = await fetch('/state');
  return await r.json();
}
async function postJSON(path, body) {
  const r = await fetch(path, {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(body || {}),
  });
  return { ok: r.ok, json: r.ok ? await r.json() : null, status: r.status, text: r.ok ? '' : await r.text() };
}

function renderLeds(counts) {
  const leds = $('leds');
  leds.innerHTML = `
    <div class="led total"><span class="bulb"></span><span class="n">${counts.total}</span><span class="label">total</span></div>
    <div class="led keep"><span class="bulb"></span><span class="n">${counts.keep}</span><span class="label">keep</span></div>
    <div class="led reject"><span class="bulb"></span><span class="n">${counts.reject}</span><span class="label">reject</span></div>
    <div class="led undecided"><span class="bulb"></span><span class="n">${counts.undecided}</span><span class="label">undecided</span></div>
  `;
}

function renderGrid() {
  const grid = $('grid');
  grid.innerHTML = '';
  const visible = visibleCandidates();
  visible.forEach((c, positionInFilter) => {
    const card = document.createElement('div');
    const classes = ['card'];
    if (c.decision) classes.push(c.decision);
    if (c.idx === state.focus) classes.push('focused');
    if (c.rejected_reason) classes.push('rejected-input');
    card.className = classes.join(' ');
    card.dataset.idx = c.idx;
    const img = document.createElement('img');
    img.loading = 'lazy';
    img.src = `/photo/${c.idx}?w=480`;
    img.alt = c.filename;
    img.addEventListener('load', () => img.classList.add('loaded'));
    card.appendChild(img);
    const idx = document.createElement('div');
    idx.className = 'idx';
    idx.textContent = String(positionInFilter + 1).padStart(2, '0');
    card.appendChild(idx);
    if (c.rejected_reason) {
      const rej = document.createElement('div');
      rej.className = 'rej-badge';
      rej.textContent = c.rejected_reason;
      card.appendChild(rej);
    } else if (c.capture_time) {
      const ct = document.createElement('div');
      ct.className = 'cap-time';
      ct.textContent = formatCaptureTime(c.capture_time);
      card.appendChild(ct);
    }
    const meta = document.createElement('div');
    meta.className = 'meta';
    const scoreBits = [];
    if (!c.rejected_reason) scoreBits.push(`q ${(c.score * 100).toFixed(0)}`);
    if (c.ai_score != null) scoreBits.push(`ai ${c.ai_score}`);
    meta.innerHTML = `<span>${c.filename}</span><span>${scoreBits.join(' · ')}</span>`;
    card.appendChild(meta);
    card.addEventListener('click', () => {
      state.focus = c.idx;
      openFocus();
      renderGrid();
      updatePos();
    });
    grid.appendChild(card);
  });
}

function focusedCard() {
  return document.querySelector(`.card[data-idx="${state.focus}"]`);
}

function scrollFocusIntoView() {
  const el = focusedCard();
  if (el) el.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

function updatePos() {
  $('pos').textContent = state.session.candidates.length
    ? `${state.focus + 1} / ${state.session.candidates.length}`
    : '';
}

async function refresh() {
  state.session = await fetchState();
  $('src').textContent = state.session.source_folder;
  renderLeds(state.session.counts);
  updateFilterCounts();
  renderGrid();
  updatePos();
}

function toast(msg, ms = 1400) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('on');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('on'), ms);
}

async function decide(decision) {
  if (!state.session) return;
  const idx = state.focus;
  const focused = state.session.candidates.find((c) => c.idx === idx);
  if (focused && focused.rejected_reason) {
    toast('cannot mark a pipeline reject — filter Pipeline rejects to rescue');
    return;
  }
  const r = await postJSON('/decision', { idx, decision });
  if (!r.ok) return toast('decision failed');
  state.session = r.json.state;
  renderLeds(state.session.counts);
  updateFilterCounts();
  renderGrid();
  updatePos();
  if (decision === 'keep' || decision === 'reject') advanceToUndecided();
}

function advanceToUndecided() {
  // Move within the current filter's visible order; skip pipeline rejects.
  const visible = visibleCandidates();
  if (!visible.length) { toast('nothing to review'); return; }
  const start = visible.findIndex((c) => c.idx === state.focus);
  const from = start >= 0 ? start : -1;
  for (let i = from + 1; i < visible.length; i++) {
    if (!visible[i].decision && !visible[i].rejected_reason) {
      state.focus = visible[i].idx; renderGrid(); scrollFocusIntoView(); updatePos(); return;
    }
  }
  for (let i = 0; i < Math.max(from, 0); i++) {
    if (!visible[i].decision && !visible[i].rejected_reason) {
      state.focus = visible[i].idx; renderGrid(); scrollFocusIntoView(); updatePos(); return;
    }
  }
  toast('all decided');
}

function move(delta) {
  const visible = visibleCandidates();
  if (!visible.length) return;
  const n = visible.length;
  let pos = visible.findIndex((c) => c.idx === state.focus);
  if (pos === -1) pos = 0;
  pos = (pos + delta + n) % n;
  state.focus = visible[pos].idx;
  renderGrid();
  scrollFocusIntoView();
  updatePos();
}

async function undo() {
  const r = await postJSON('/undo');
  if (!r.ok) return toast('nothing to undo');
  if (r.json.undone_idx == null) return toast('nothing to undo');
  state.session = r.json.state;
  state.focus = r.json.undone_idx;
  renderLeds(state.session.counts);
  updateFilterCounts();
  renderGrid();
  scrollFocusIntoView();
  updatePos();
  toast('undone');
}

function qualityPercentile(c) {
  // 1-based rank of this photo's composite score among the session's pipeline
  // keepers, as "top N%". Client-side only — the score list is already here.
  const scores = state.session.candidates
    .filter((x) => !x.rejected_reason)
    .map((x) => x.score || 0)
    .sort((a, b) => b - a);
  if (!scores.length) return null;
  let rank = scores.findIndex((s) => s <= (c.score || 0)) + 1;
  if (rank === 0) rank = scores.length;
  return Math.max(1, Math.round((rank / scores.length) * 100));
}

function openFocus() {
  if (!state.session || !state.session.candidates.length) return;
  const c = state.session.candidates.find((x) => x.idx === state.focus)
         || state.session.candidates[0];
  if (!c) return;
  state.focus = c.idx;
  $('focus-img').src = `/photo/${c.idx}?w=1200`;
  $('focus-name').textContent = c.filename;
  if (c.rejected_reason) {
    // Pipeline reject — its 0.0 score is a sentinel, not a measurement.
    $('focus-quality').style.display = 'none';
    $('focus-culled').style.display = '';
    $('focus-reject-reason').textContent = c.rejected_reason;
  } else {
    $('focus-quality').style.display = '';
    $('focus-culled').style.display = 'none';
    $('focus-score').textContent = (c.score * 100).toFixed(0);
    const pct = qualityPercentile(c);
    $('focus-pct').textContent = pct != null ? `· top ${pct}% of this shoot` : '';
  }
  if (c.ai_score != null) {
    $('focus-ai').style.display = '';
    $('focus-ai-score').textContent = c.ai_score;
    $('focus-ai-reason').textContent = c.ai_reason || '';
  } else {
    $('focus-ai').style.display = 'none';
    $('focus-ai-reason').textContent = '';
  }
  $('focus-capture').textContent = c.capture_time ? formatCaptureTime(c.capture_time) : '';
  $('focus-view').classList.add('on');
}
function closeFocus() { $('focus-view').classList.remove('on'); }
function toggleFocus() {
  if ($('focus-view').classList.contains('on')) closeFocus(); else openFocus();
}

function openExport() {
  $('export-result').style.display = 'none';
  $('export-result').classList.remove('err');
  $('export-target').value = state.session ? (state.session.source_folder + '/keepers') : '';
  $('export-dialog').classList.add('on');
  setTimeout(() => $('export-target').focus(), 50);
}
function closeExport() { $('export-dialog').classList.remove('on'); }

async function runExport() {
  const target = $('export-target').value.trim();
  if (!target) return;
  const body = {
    target,
    include_undecided: $('export-undecided').checked,
    convert_heic: !$('export-no-convert').checked,
    write_manifest: $('export-manifest').checked,
    xmp: $('export-xmp').checked,
  };
  const r = await postJSON('/export', body);
  const box = $('export-result');
  box.style.display = 'block';
  if (!r.ok) {
    box.classList.add('err');
    box.textContent = 'Export failed: ' + (r.text || r.status);
    return;
  }
  const j = r.json;
  box.classList.remove('err');
  let msg = `Copied ${j.exported} keepers → ${j.target}`;
  if (j.manifest_written) msg += ` (+ ${j.manifest_written})`;
  if (j.xmp_embedded != null) msg += ` · ${j.xmp_embedded} XMP-rated`;
  if (j.override) msg += ` · ${j.override.line}`;
  box.textContent = msg;
  toast(msg);
}

function openHelp() { $('help-dialog').classList.add('on'); }
function closeHelp() { $('help-dialog').classList.remove('on'); }

document.addEventListener('keydown', (ev) => {
  if (ev.target.tagName === 'INPUT') return;
  const key = ev.key.toLowerCase();
  if ($('export-dialog').classList.contains('on')) {
    if (key === 'escape') closeExport();
    return;
  }
  if ($('help-dialog').classList.contains('on')) {
    if (key === 'escape' || key === '?') closeHelp();
    return;
  }
  if ($('focus-view').classList.contains('on')) {
    if (key === 'escape' || key === 'enter') { closeFocus(); ev.preventDefault(); return; }
    if (key === 'k') { decide('keep'); ev.preventDefault(); return; }
    if (key === 'x') { decide('reject'); ev.preventDefault(); return; }
    if (key === 'arrowleft') { move(-1); openFocus(); ev.preventDefault(); return; }
    if (key === 'arrowright') { move(1); openFocus(); ev.preventDefault(); return; }
    return;
  }
  if (key === 'k') { decide('keep'); ev.preventDefault(); }
  else if (key === 'x') { decide('reject'); ev.preventDefault(); }
  else if (key === 'u') { undo(); ev.preventDefault(); }
  else if (key === 'arrowleft') { move(-1); ev.preventDefault(); }
  else if (key === 'arrowright') { move(1); ev.preventDefault(); }
  else if (key === 'arrowup') { move(-4); ev.preventDefault(); }
  else if (key === 'arrowdown') { move(4); ev.preventDefault(); }
  else if (key === 'enter') { toggleFocus(); ev.preventDefault(); }
  else if (key === 'e') { openExport(); ev.preventDefault(); }
  else if (key === 'f') { cycleFilter(); ev.preventDefault(); }
  else if (key === '?') { openHelp(); ev.preventDefault(); }
  else if (key === 'escape') { closeFocus(); }
});

function cycleFilter() {
  const chips = Array.from(document.querySelectorAll('#filters .chip'))
    .filter((c) => c.style.display !== 'none');
  const currentIdx = chips.findIndex((c) => c.classList.contains('on'));
  const nextIdx = (currentIdx + 1) % chips.length;
  chips[nextIdx].click();
  toast(`filter: ${chips[nextIdx].dataset.filter}`);
}

$('btn-undo').addEventListener('click', undo);
$('btn-export').addEventListener('click', openExport);
$('btn-help').addEventListener('click', openHelp);
$('export-cancel').addEventListener('click', closeExport);
$('export-run').addEventListener('click', runExport);
$('help-close').addEventListener('click', closeHelp);
$('focus-view').addEventListener('click', (ev) => {
  if (ev.target.id === 'focus-view') closeFocus();
});

// Filter chips
document.querySelectorAll('#filters .chip').forEach((el) => {
  el.addEventListener('click', () => {
    document.querySelectorAll('#filters .chip').forEach((c) => c.classList.remove('on'));
    el.classList.add('on');
    state.filter = el.dataset.filter;
    renderGrid();
    updatePos();
  });
});

// Sort dropdown
$('sort-select').addEventListener('change', (ev) => {
  state.sort = ev.target.value;
  renderGrid();
  updatePos();
});

async function bootstrap() {
  // Read progress first — if it's not finished yet, show the progress screen
  // until finished:true arrives on the SSE stream.
  try {
    const r = await fetch('/progress');
    if (r.ok) {
      const snap = await r.json();
      if (!snap.finished) {
        showProgressScreen(snap);
        subscribeProgress();
        return;
      }
    }
  } catch (e) {
    // fall through
  }
  await refresh();
}

function showProgressScreen(snap) {
  $('progress-screen').classList.add('on');
  updateProgress(snap);
}

function hideProgressScreen() {
  $('progress-screen').classList.remove('on');
}

function updateProgress(snap) {
  const stage = (snap.stage || 'starting').replace(/-/g, ' ');
  $('prog-stage').textContent = stage;
  const pct = snap.total > 0 ? Math.round((snap.done / snap.total) * 100) : 0;
  $('prog-fill').style.width = pct + '%';
  $('prog-counts').textContent = `${snap.done} / ${snap.total}`;
}

function subscribeProgress() {
  const es = new EventSource('/progress/stream');
  es.onmessage = (ev) => {
    try {
      const snap = JSON.parse(ev.data);
      updateProgress(snap);
      if (snap.finished) {
        es.close();
        hideProgressScreen();
        refresh();
      }
    } catch (e) { /* ignore */ }
  };
  es.onerror = () => {
    // Server closed the connection or network hiccup — refetch state.
    es.close();
    setTimeout(async () => {
      const st = await fetchState();
      if (st.counts && st.counts.total > 0) {
        hideProgressScreen();
        state.session = st;
        renderLeds(state.session.counts);
        updateFilterCounts();
        renderGrid();
        updatePos();
      } else {
        subscribeProgress();
      }
    }, 500);
  };
}

bootstrap();
</script>
</body>
</html>
"""
