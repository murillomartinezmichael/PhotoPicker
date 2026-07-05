from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from photopicker.webui import (
    Candidate,
    Session,
    SessionStore,
    _build_export_manifest,
    _load_session_from_disk,
    build_session,
)


def _make(root: Path, name: str, seed: int = 0) -> Path:
    p = root / name
    arr = np.full((600, 600, 3), 128, dtype=np.uint8)
    arr[seed % 500 : (seed % 500) + 100, :] = 255
    Image.fromarray(arr).save(p)
    return p


# --- build_session -----------------------------------------------------------


def test_build_session_wraps_keepers(tmp_path: Path):
    a = _make(tmp_path, "a.png", 1)
    b = _make(tmp_path, "b.png", 2)

    session = build_session(
        source_folder=tmp_path,
        keepers=[a, b],
        scores={a: 0.8, b: 0.5},
        reject_summary={"blurry": 3},
        input_count=10,
        prompt="pretty photos",
    )

    assert session.source_folder == str(tmp_path)
    assert len(session.candidates) == 2
    assert session.candidates[0].path == str(a)
    assert session.candidates[0].filename == "a.png"
    assert session.candidates[0].score == pytest.approx(0.8)
    assert session.candidates[0].idx == 0
    assert session.prompt == "pretty photos"
    assert session.reject_summary == {"blurry": 3}
    assert session.input_count == 10


def test_build_session_carries_ai_scores(tmp_path: Path):
    a = _make(tmp_path, "a.png", 1)

    session = build_session(
        source_folder=tmp_path,
        keepers=[a],
        scores={a: 0.7},
        ai_scores={a: (88, "sharp deck")},
    )

    assert session.candidates[0].ai_score == 88
    assert session.candidates[0].ai_reason == "sharp deck"


def test_build_session_restores_prior_decisions(tmp_path: Path):
    a = _make(tmp_path, "a.png", 1)
    b = _make(tmp_path, "b.png", 2)
    (tmp_path / ".photopicker-session.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {"path": str(a), "decision": "keep"},
                    {"path": str(b), "decision": "reject"},
                ]
            }
        )
    )

    session = build_session(source_folder=tmp_path, keepers=[a, b])

    assert session.candidates[0].decision == "keep"
    assert session.candidates[1].decision == "reject"


def test_build_session_ignores_prior_paths_that_no_longer_match(tmp_path: Path):
    a = _make(tmp_path, "a.png", 1)
    (tmp_path / ".photopicker-session.json").write_text(
        json.dumps(
            {"candidates": [{"path": "/nowhere/x.png", "decision": "keep"}]}
        )
    )

    session = build_session(source_folder=tmp_path, keepers=[a])

    assert session.candidates[0].decision == ""


def test_load_session_from_disk_handles_missing_file(tmp_path: Path):
    candidates = [Candidate(idx=0, path="/x", filename="x")]
    got = _load_session_from_disk(tmp_path / "nope.json", candidates)
    assert got == candidates


def test_build_session_include_rejects_appends_with_reason(tmp_path: Path):
    keeper = _make(tmp_path, "keep.png", 1)
    bad = _make(tmp_path, "blur.png", 2)
    tiny = _make(tmp_path, "tiny.png", 3)

    session = build_session(
        source_folder=tmp_path,
        keepers=[keeper],
        scores={keeper: 0.7},
        include_rejects={"blurry": [bad], "too_small": [tiny]},
    )

    assert len(session.candidates) == 3
    kept, rejected = [], []
    for c in session.candidates:
        (kept if not c.rejected_reason else rejected).append(c)
    assert len(kept) == 1
    assert kept[0].filename == "keep.png"
    reasons = {c.rejected_reason for c in rejected}
    assert reasons == {"blurry", "too_small"}


def test_build_session_include_rejects_skips_unreadable_and_dedupes(tmp_path: Path):
    keeper = _make(tmp_path, "keep.png", 1)
    dup = _make(tmp_path, "dup.png", 2)
    other = _make(tmp_path, "other.png", 3)

    session = build_session(
        source_folder=tmp_path,
        keepers=[keeper],
        include_rejects={
            "duplicates": [dup, dup],   # same twice → dedupes
            "unreadable": [other],       # dropped entirely
        },
    )

    assert len(session.candidates) == 2
    reasons = [c.rejected_reason for c in session.candidates[1:]]
    assert reasons == ["duplicates"]


def test_build_session_populates_capture_time_when_present(tmp_path: Path):
    """Files without EXIF get None; that's fine."""
    keeper = _make(tmp_path, "no_exif.png", 1)
    session = build_session(source_folder=tmp_path, keepers=[keeper])
    assert session.candidates[0].capture_time is None


def test_build_export_manifest_shape(tmp_path: Path):
    session = Session(
        source_folder=str(tmp_path),
        candidates=[
            Candidate(idx=0, path=str(tmp_path / "a.png"), filename="a.png",
                      score=0.8, decision="keep", capture_time="2026-07-05T12:00:00"),
            Candidate(idx=1, path=str(tmp_path / "b.png"), filename="b.png",
                      score=0.5, decision="keep", ai_score=88, ai_reason="strong"),
        ],
        prompt="best photos",
        input_count=20,
        reject_summary={"blurry": 3},
    )
    src_to_dest = {
        Path(str(tmp_path / "a.png")): Path(str(tmp_path / "out/a.png")),
        Path(str(tmp_path / "b.png")): Path(str(tmp_path / "out/b.png")),
    }

    manifest = _build_export_manifest(session, src_to_dest, tmp_path / "out")

    assert manifest["prompt"] == "best photos"
    assert manifest["input_count"] == 20
    assert manifest["exported_count"] == 2
    assert manifest["reject_summary"] == {"blurry": 3}
    picks = manifest["picks"]
    assert len(picks) == 2
    assert picks[0]["source_filename"] == "a.png"
    assert picks[0]["output_filename"] == "a.png"
    assert picks[0]["decision"] == "keep"
    assert picks[0]["capture_time"] == "2026-07-05T12:00:00"
    assert picks[1]["ai_score"] == 88
    assert picks[1]["ai_reason"] == "strong"


def test_load_session_from_disk_handles_corrupt_json(tmp_path: Path):
    sf = tmp_path / "corrupt.json"
    sf.write_text("{not json")
    candidates = [Candidate(idx=0, path="/x", filename="x")]
    got = _load_session_from_disk(sf, candidates)
    assert got == candidates


# --- SessionStore ------------------------------------------------------------


def _fresh_store(tmp_path: Path, n: int = 3) -> tuple[SessionStore, list[Path]]:
    paths = [_make(tmp_path, f"p{i}.png", i) for i in range(n)]
    session = build_session(source_folder=tmp_path, keepers=paths)
    store = SessionStore(session=session, session_path=tmp_path / ".photopicker-session.json")
    return store, paths


def test_store_decide_records_and_persists(tmp_path: Path):
    store, _ = _fresh_store(tmp_path)

    store.decide(0, "keep")
    store.decide(1, "reject")

    counts = store.get().counts()
    assert counts["keep"] == 1
    assert counts["reject"] == 1
    assert counts["undecided"] == 1
    on_disk = json.loads((tmp_path / ".photopicker-session.json").read_text())
    decisions = [c["decision"] for c in on_disk["candidates"]]
    assert decisions == ["keep", "reject", ""]


def test_store_undo_reverts_last(tmp_path: Path):
    store, _ = _fresh_store(tmp_path)
    store.decide(0, "keep")
    store.decide(1, "reject")

    idx = store.undo()

    assert idx == 1
    session = store.get()
    assert session.candidates[1].decision == ""
    assert session.candidates[0].decision == "keep"


def test_store_undo_empty_returns_none(tmp_path: Path):
    store, _ = _fresh_store(tmp_path)
    assert store.undo() is None


def test_store_reset_clears_all(tmp_path: Path):
    store, _ = _fresh_store(tmp_path)
    store.decide(0, "keep")
    store.decide(1, "keep")

    store.reset()

    for c in store.get().candidates:
        assert c.decision == ""
    assert store.get().history == []


def test_store_decide_rejects_bad_decision(tmp_path: Path):
    store, _ = _fresh_store(tmp_path)
    with pytest.raises(ValueError):
        store.decide(0, "maybe")


def test_store_decide_rejects_out_of_range_idx(tmp_path: Path):
    store, _ = _fresh_store(tmp_path)
    with pytest.raises(IndexError):
        store.decide(99, "keep")


def test_store_keepers_returns_only_kept(tmp_path: Path):
    store, paths = _fresh_store(tmp_path)
    store.decide(0, "keep")
    store.decide(2, "keep")
    store.decide(1, "reject")

    keepers = store.keepers()

    assert set(keepers) == {paths[0], paths[2]}


def test_store_undecided_keepers_includes_undecided(tmp_path: Path):
    store, paths = _fresh_store(tmp_path)
    store.decide(1, "reject")

    keepers = store.undecided_keepers()

    assert set(keepers) == {paths[0], paths[2]}


# --- HTTP server (integration) -----------------------------------------------


def _start_server(store: SessionStore, port: int) -> tuple[threading.Thread, threading.Event]:
    from http.server import ThreadingHTTPServer

    from photopicker.webui import _ThumbCache, make_handler

    thumb_cache = _ThumbCache()
    shutdown_event = threading.Event()
    handler_cls = make_handler(store, thumb_cache, shutdown_event)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler_cls)

    def run():
        httpd.serve_forever()

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def stop():
        httpd.shutdown()
        httpd.server_close()

    shutdown_event.stop = stop  # type: ignore[attr-defined]
    return t, shutdown_event


def _http_get(url: str) -> tuple[int, bytes, str]:
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), exc.headers.get("Content-Type", "") if exc.headers else ""


def _http_post(url: str, body: dict) -> tuple[int, dict | str]:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode()
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode() if exc.fp else ""
        return exc.code, raw


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def running_server(tmp_path: Path):
    store, paths = _fresh_store(tmp_path, n=4)
    port = _free_port()
    _, shutdown = _start_server(store, port)
    # Server is on its own thread; loopback binds immediately but give the
    # accept loop a beat.
    time.sleep(0.05)
    yield f"http://127.0.0.1:{port}", store, paths
    shutdown.stop()  # type: ignore[attr-defined]


def test_http_state_returns_session(running_server):
    base, store, _ = running_server
    status, body, ctype = _http_get(f"{base}/state")
    assert status == 200
    assert "application/json" in ctype
    payload = json.loads(body)
    assert payload["counts"]["total"] == 4


def test_http_root_returns_html(running_server):
    base, _, _ = running_server
    status, body, ctype = _http_get(f"{base}/")
    assert status == 200
    assert "text/html" in ctype
    assert b"photopicker" in body
    assert b"cull" in body


def test_http_photo_returns_jpeg_bytes(running_server):
    base, _, _ = running_server
    status, body, ctype = _http_get(f"{base}/photo/0?w=200")
    assert status == 200
    assert ctype.startswith("image/jpeg")
    assert body[:3] == b"\xff\xd8\xff"  # JPEG magic bytes


def test_http_photo_bad_idx_returns_400(running_server):
    base, _, _ = running_server
    status, _, _ = _http_get(f"{base}/photo/not-a-num")
    assert status == 400


def test_http_photo_out_of_range_returns_404(running_server):
    base, _, _ = running_server
    status, _, _ = _http_get(f"{base}/photo/999")
    assert status == 404


def test_http_decision_persists_to_store(running_server):
    base, store, _ = running_server
    status, payload = _http_post(f"{base}/decision", {"idx": 0, "decision": "keep"})
    assert status == 200
    assert isinstance(payload, dict)
    assert payload["ok"] is True
    assert store.get().candidates[0].decision == "keep"


def test_http_decision_bad_input_returns_400(running_server):
    base, _, _ = running_server
    status, _ = _http_post(f"{base}/decision", {"idx": 0, "decision": "maybe"})
    assert status == 400


def test_http_undo_reverts_last(running_server):
    base, store, _ = running_server
    _http_post(f"{base}/decision", {"idx": 0, "decision": "keep"})
    status, payload = _http_post(f"{base}/undo", {})
    assert status == 200
    assert payload["undone_idx"] == 0
    assert store.get().candidates[0].decision == ""


def test_http_reset_clears_all(running_server):
    base, store, _ = running_server
    _http_post(f"{base}/decision", {"idx": 0, "decision": "keep"})
    _http_post(f"{base}/decision", {"idx": 1, "decision": "reject"})

    status, _ = _http_post(f"{base}/reset", {})

    assert status == 200
    for c in store.get().candidates:
        assert c.decision == ""


def test_http_export_copies_keepers(tmp_path: Path, running_server):
    base, _, _ = running_server
    _http_post(f"{base}/decision", {"idx": 0, "decision": "keep"})
    _http_post(f"{base}/decision", {"idx": 1, "decision": "reject"})

    target = tmp_path / "exported"
    status, payload = _http_post(
        f"{base}/export", {"target": str(target), "include_undecided": False}
    )

    assert status == 200
    assert payload["exported"] == 1
    assert target.exists()
    assert len(list(target.iterdir())) == 1


def test_http_export_include_undecided(tmp_path: Path, running_server):
    base, _, _ = running_server
    _http_post(f"{base}/decision", {"idx": 1, "decision": "reject"})

    target = tmp_path / "with_undecided"
    status, payload = _http_post(
        f"{base}/export", {"target": str(target), "include_undecided": True}
    )

    assert status == 200
    # 4 total - 1 reject = 3 exported (0, 2, 3)
    assert payload["exported"] == 3


def test_http_export_requires_target(running_server):
    base, _, _ = running_server
    status, _ = _http_post(f"{base}/export", {})
    assert status == 400


def test_http_export_nothing_to_export(tmp_path: Path, running_server):
    base, _, _ = running_server
    # Reject all so keepers() is empty; include_undecided False.
    for i in range(4):
        _http_post(f"{base}/decision", {"idx": i, "decision": "reject"})

    target = tmp_path / "empty_export"
    status, payload = _http_post(f"{base}/export", {"target": str(target)})

    assert status == 200
    assert payload["exported"] == 0


def test_http_unknown_route_returns_404(running_server):
    base, _, _ = running_server
    status, _, _ = _http_get(f"{base}/nope")
    assert status == 404


def test_http_export_writes_manifest_when_flag_set(tmp_path: Path, running_server):
    base, _, _ = running_server
    _http_post(f"{base}/decision", {"idx": 0, "decision": "keep"})
    _http_post(f"{base}/decision", {"idx": 2, "decision": "keep"})

    target = tmp_path / "keepers_with_manifest"
    status, payload = _http_post(
        f"{base}/export",
        {"target": str(target), "write_manifest": True},
    )

    assert status == 200
    assert payload["exported"] == 2
    assert payload.get("manifest_written") == "manifest.json"
    manifest_path = target / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["exported_count"] == 2
    assert len(manifest["picks"]) == 2


def test_http_export_without_manifest_flag_skips(tmp_path: Path, running_server):
    base, _, _ = running_server
    _http_post(f"{base}/decision", {"idx": 0, "decision": "keep"})

    target = tmp_path / "keepers_no_manifest"
    status, payload = _http_post(f"{base}/export", {"target": str(target)})

    assert status == 200
    assert "manifest_written" not in payload
    assert not (target / "manifest.json").exists()
