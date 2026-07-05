"""RUNG 6 UPGRADE tests — CullProgressBroker mechanics.

Broker is the thread-safe pub/sub between the background cull thread (producer)
and the /progress/stream SSE consumers. Tests lock the invariants:

- update() bumps serial only on real change (dedupe)
- wait_for_change unblocks the moment a new state arrives
- mark_finished sets finished=True and unblocks everyone
- multiple waiters all receive the same snapshot
"""
from __future__ import annotations

import threading
import time

from photopicker.webui import CullProgressBroker


def test_broker_initial_snapshot():
    b = CullProgressBroker()
    snap = b.snapshot()
    assert snap["stage"] == ""
    assert snap["done"] == 0
    assert snap["total"] == 0
    assert snap["finished"] is False
    assert snap["serial"] == 0


def test_broker_update_bumps_serial_on_change():
    b = CullProgressBroker()
    s0 = b.snapshot()["serial"]
    b.update("scoring", 10, 100)
    s1 = b.snapshot()["serial"]
    b.update("scoring", 20, 100)
    s2 = b.snapshot()["serial"]
    assert s1 > s0
    assert s2 > s1


def test_broker_update_dedupes_identical_state():
    b = CullProgressBroker()
    b.update("scoring", 10, 100)
    s = b.snapshot()["serial"]
    b.update("scoring", 10, 100)  # same tuple
    b.update("scoring", 10, 100)
    assert b.snapshot()["serial"] == s


def test_broker_mark_finished_bumps_serial_and_sets_flag():
    b = CullProgressBroker()
    s0 = b.snapshot()["serial"]
    b.mark_finished()
    snap = b.snapshot()
    assert snap["finished"] is True
    assert snap["serial"] > s0


def test_broker_mark_finished_is_idempotent():
    b = CullProgressBroker()
    b.mark_finished()
    s = b.snapshot()["serial"]
    b.mark_finished()
    assert b.snapshot()["serial"] == s


def test_broker_wait_for_change_returns_immediately_when_ahead():
    b = CullProgressBroker()
    b.update("scoring", 5, 10)
    got = b.wait_for_change(last_serial=-1, timeout=0.5)
    assert got["stage"] == "scoring"
    assert got["done"] == 5
    assert got["total"] == 10


def test_broker_wait_for_change_unblocks_on_producer():
    b = CullProgressBroker()

    got: dict = {}

    def _consume():
        got.update(b.wait_for_change(last_serial=0, timeout=2.0))

    t = threading.Thread(target=_consume, daemon=True)
    t.start()
    time.sleep(0.05)  # let the consumer park on the condition
    b.update("dedup", 42, 100)
    t.join(timeout=1.0)
    assert not t.is_alive()
    assert got["stage"] == "dedup"
    assert got["done"] == 42


def test_broker_wait_for_change_wakes_on_finish():
    b = CullProgressBroker()
    seen: dict = {}

    def _consume():
        seen.update(b.wait_for_change(last_serial=0, timeout=2.0))

    t = threading.Thread(target=_consume, daemon=True)
    t.start()
    time.sleep(0.05)
    b.mark_finished()
    t.join(timeout=1.0)
    assert seen["finished"] is True


def test_broker_multiple_waiters_all_receive_update():
    b = CullProgressBroker()
    results: list[dict] = []
    lock = threading.Lock()

    def _consume():
        snap = b.wait_for_change(last_serial=0, timeout=2.0)
        with lock:
            results.append(snap)

    threads = [threading.Thread(target=_consume, daemon=True) for _ in range(4)]
    for t in threads:
        t.start()
    time.sleep(0.05)
    b.update("scoring", 3, 5)
    for t in threads:
        t.join(timeout=1.0)
    assert len(results) == 4
    assert all(r["done"] == 3 for r in results)
