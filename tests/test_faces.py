"""Tests for `photopicker.faces` — MediaPipe Face Mesh face/closed-eye signal.

Requires the `faces` extra (`pip install "photopicker[faces]"`); skipped
entirely otherwise, matching the CLIP/vision optional-dependency pattern —
the core suite must never require a heavy opt-in dependency.

No real labeled face photos exist in this repo's fixtures (a photo-culling
tool for construction sites has no reason to carry portrait test data), so
these tests draw simple, clearly-synthetic faces with PIL (an oval + drawn
eyes) — honestly a stand-in for unit-testing purposes only, not a claim about
real-world portrait accuracy. Verified manually against MediaPipe before
writing these tests: the open-eye synthetic face returns EAR ~0.46, the
closed-eye variant ~0.17 (published closed-eye threshold is 0.2), and a
plain checkerboard returns no face at all — so the geometry check is real,
even though the input photos are drawn, not photographed.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

mp_pytest = pytest.importorskip("mediapipe", reason="requires photopicker[faces]")

from photopicker.culler import cull  # noqa: E402
from photopicker.faces import (  # noqa: E402
    CLOSED_EYE_PENALTY,
    face_eye_score,
)

_SIZE = 900


def _draw_face(eye_open: bool, bg_sharpness: int = 0) -> np.ndarray:
    """A drawn oval face with either open (circle) or closed (line) eyes.

    `bg_sharpness` overlays a faint checkerboard *outside the face oval only*
    so two photos can be given deliberately different overall quality scores
    (to exercise culler ranking) without disturbing the face/eye region
    MediaPipe reads landmarks from — 0 = none, higher = a sharper-looking
    background.
    """
    img = Image.new("RGB", (_SIZE, _SIZE), (200, 170, 140))
    d = ImageDraw.Draw(img)
    scale = _SIZE / 400
    d.ellipse([80 * scale, 60 * scale, 320 * scale, 340 * scale], fill=(220, 190, 160))
    if eye_open:
        d.ellipse([140 * scale, 160 * scale, 180 * scale, 185 * scale], fill=(255, 255, 255))
        d.ellipse([155 * scale, 165 * scale, 170 * scale, 180 * scale], fill=(30, 30, 30))
        d.ellipse([220 * scale, 160 * scale, 260 * scale, 185 * scale], fill=(255, 255, 255))
        d.ellipse([235 * scale, 165 * scale, 250 * scale, 180 * scale], fill=(30, 30, 30))
    else:
        d.line([140 * scale, 172 * scale, 180 * scale, 172 * scale], fill=(80, 50, 40), width=int(4 * scale))
        d.line([220 * scale, 172 * scale, 260 * scale, 172 * scale], fill=(80, 50, 40), width=int(4 * scale))
    d.line([135 * scale, 145 * scale, 185 * scale, 140 * scale], fill=(90, 60, 40), width=int(6 * scale))
    d.line([215 * scale, 140 * scale, 265 * scale, 145 * scale], fill=(90, 60, 40), width=int(6 * scale))
    d.line([200 * scale, 190 * scale, 190 * scale, 240 * scale], fill=(180, 140, 110), width=int(4 * scale))
    d.arc([160 * scale, 250 * scale, 240 * scale, 290 * scale], start=20, end=160, fill=(150, 60, 60), width=int(5 * scale))

    arr = np.array(img)
    face_x0, face_x1 = int(80 * scale), int(320 * scale)
    face_y0, face_y1 = int(60 * scale), int(340 * scale)
    if bg_sharpness:
        for r in range(0, _SIZE, 20):
            for c in range(0, _SIZE, 20):
                if face_y0 <= r <= face_y1 and face_x0 <= c <= face_x1:
                    continue  # leave the face oval untouched
                if (r // 20 + c // 20) % 2 == 0:
                    arr[r : r + 10, c : c + 10] = np.clip(
                        arr[r : r + 10, c : c + 10].astype(int) + bg_sharpness, 0, 255
                    ).astype(np.uint8)
    return arr


def _checkerboard(tmp_path: Path, name: str) -> Path:
    arr = np.zeros((_SIZE, _SIZE, 3), dtype=np.uint8)
    for r in range(0, _SIZE, 16):
        for c in range(0, _SIZE, 16):
            if (r // 16 + c // 16) % 2 == 0:
                arr[r : r + 16, c : c + 16] = 255
    p = tmp_path / name
    Image.fromarray(arr).save(p)
    return p


def _face_photo(tmp_path: Path, name: str, eye_open: bool, bg_sharpness: int = 0) -> Path:
    arr = _draw_face(eye_open, bg_sharpness)
    p = tmp_path / name
    Image.fromarray(arr).save(p)
    return p


def test_no_crash_and_no_face_on_non_face_image(tmp_path: Path):
    """Detection must run without crashing on ordinary (non-portrait) photos
    and must not penalize them — most culled photos have no people in them."""
    path = _checkerboard(tmp_path, "checker.png")
    result = face_eye_score(path)
    assert result.face_found is False
    assert result.score == 1.0
    assert result.eyes_closed is False


def test_unreadable_file_returns_neutral_not_a_crash(tmp_path: Path):
    bogus = tmp_path / "not_an_image.png"
    bogus.write_bytes(b"not actually an image")
    result = face_eye_score(bogus)
    assert result.face_found is False
    assert result.score == 1.0


def test_open_eyes_detected_as_open(tmp_path: Path):
    path = _face_photo(tmp_path, "open.png", eye_open=True)
    result = face_eye_score(path)
    assert result.face_found is True
    assert result.num_faces == 1
    assert result.eyes_closed is False
    assert result.score == 1.0
    assert result.min_ear is not None and result.min_ear > 0.2


def test_closed_eyes_detected_as_closed(tmp_path: Path):
    path = _face_photo(tmp_path, "closed.png", eye_open=False)
    result = face_eye_score(path)
    assert result.face_found is True
    assert result.eyes_closed is True
    assert result.score == CLOSED_EYE_PENALTY
    assert result.min_ear is not None and result.min_ear < 0.2


def test_open_ear_clearly_higher_than_closed_ear(tmp_path: Path):
    """Direct regression check on the published EAR technique: an open eye
    should score meaningfully higher than a closed one on the same face."""
    open_result = face_eye_score(_face_photo(tmp_path, "open2.png", eye_open=True))
    closed_result = face_eye_score(_face_photo(tmp_path, "closed2.png", eye_open=False))
    assert open_result.min_ear > closed_result.min_ear


def _burst_pair(tmp_path: Path) -> tuple[Path, Path]:
    """Two frames of the 'same shot' — same face/pose, close in perceptual
    hash (a real closed-eye burst pair would be too) — but with the closed-
    eye frame given a slightly sharper background so it wins on raw quality
    alone. This is the realistic case the feature exists for: a burst where
    the sharper frame happens to be the one where the subject blinked.
    """
    open_path = _face_photo(tmp_path, "open.png", eye_open=True, bg_sharpness=10)
    closed_path = _face_photo(tmp_path, "closed.png", eye_open=False, bg_sharpness=40)
    return open_path, closed_path


def test_cull_face_gate_off_by_default_keeps_sharper_closed_eye_frame(tmp_path: Path):
    """Without --faces/face_gate, the sharper (closed-eye) frame of a burst
    pair still wins the perceptual-dedup tiebreak — existing behavior must
    not change for callers who don't opt in."""
    open_path, closed_path = _burst_pair(tmp_path)

    result = cull([open_path, closed_path], top_n=2, face_gate=False)

    assert result.keepers == [closed_path]
    assert result.clusters[closed_path] == [open_path]


def test_cull_face_gate_on_downranks_closed_eyes(tmp_path: Path):
    """With face_gate=True, the closed-eye penalty flips which frame of the
    same burst pair wins: the open-eye frame is kept instead."""
    open_path, closed_path = _burst_pair(tmp_path)

    baseline = cull([open_path, closed_path], top_n=2, face_gate=False)
    gated = cull([open_path, closed_path], top_n=2, face_gate=True)

    assert baseline.keepers == [closed_path]  # sanity: closed really wins pre-gate
    assert gated.keepers == [open_path]
    assert gated.clusters[open_path] == [closed_path]
    assert gated.scores[open_path] == pytest.approx(baseline.all_scores[open_path])
