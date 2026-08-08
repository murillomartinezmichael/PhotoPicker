"""Face + eye-open/closed detection — MediaPipe Face Mesh (Apache License 2.0).

Opt-in signal (`pip install "photopicker[faces]"`). Detects whether a photo
has a face and, if so, whether the eyes are open or closed, using the
published Eye Aspect Ratio (EAR) technique (Soukupova & Cech, 2016) against
MediaPipe's iris-refined face-mesh landmarks. No training and no labeled
data needed — EAR is a deterministic geometry check once landmarks are in
hand, which is exactly why this profile-decision picked a pretrained
landmark model over training a custom open/closed classifier.

Scope: this is NOT face recognition/identity. It answers exactly two
questions for the culler: (a) is there a face, (b) are the eyes open. Photos
with no face score neutral (1.0, no penalty) — landscapes/buildings/detail
shots are the bulk of a construction-site shoot and must never be
down-ranked for lacking a person.

License: `mediapipe` is Google's Apache License 2.0 (confirmed via package
METADATA + LICENSE file at time of integration, 2026-07). No research-only
or non-commercial restriction — safe for this commercial product.

Version pin: `mediapipe==0.10.21`. mediapipe 0.10.22+ removed the legacy
`mediapipe.python.solutions.face_mesh` API this module depends on, in favor
of a newer Tasks API that downloads model assets from Google's servers at
runtime. 0.10.21 ships the `.tflite` face-landmark model *inside the wheel*
— fully offline, matching this project's deterministic, no-network pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

# Standard MediaPipe Face Mesh landmark indices used for Eye Aspect Ratio.
# h1/h2 = horizontal eye corners, v1/v2 = two vertical lid pairs.
_LEFT_EYE = {"h1": 33, "h2": 133, "v1_top": 160, "v1_bot": 144, "v2_top": 158, "v2_bot": 153}
_RIGHT_EYE = {"h1": 362, "h2": 263, "v1_top": 385, "v1_bot": 380, "v2_top": 387, "v2_bot": 373}

# Published blink/closed threshold (Soukupova & Cech, 2016). Below this the
# eye is closed; open eyes on real faces typically land 0.25-0.35+.
CLOSED_EYE_EAR_THRESHOLD = 0.2

# Score multiplier applied when the worst detected face has closed eyes.
# Not zero — a closed-eye group photo shouldn't be a hard reject (that is
# the quality gate's job), just down-ranked against an otherwise-equal frame
# with open eyes.
CLOSED_EYE_PENALTY = 0.4

MAX_FACES = 5

_face_mesh_singleton = None


def _install_hint() -> str:
    return 'pip install "photopicker[faces]"'


def _get_face_mesh():
    """Lazy-load the MediaPipe FaceMesh model once per process.

    Mirrors `ClipClassifier._load()` — the core package must import cleanly
    with no `mediapipe` installed; only code paths that opt into this signal
    pay the (real) dependency cost.
    """
    global _face_mesh_singleton
    if _face_mesh_singleton is None:
        try:
            import mediapipe as mp
        except ImportError as exc:
            raise ImportError(
                f"Face/eye detection needs the 'faces' extra: {_install_hint()}"
            ) from exc
        _face_mesh_singleton = mp.solutions.face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=MAX_FACES,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        )
    return _face_mesh_singleton


@dataclass
class FaceEyeResult:
    face_found: bool
    num_faces: int = 0
    min_ear: float | None = None  # worst (most-closed) eye-aspect-ratio across all faces
    eyes_closed: bool = False  # True if the worst detected face is below threshold
    score: float = 1.0  # multiplier for composite scoring; 1.0 = no penalty


def _eye_aspect_ratio(landmarks, eye: dict[str, int], w: int, h: int) -> float:
    def pt(idx: int) -> np.ndarray:
        lm = landmarks[idx]
        return np.array([lm.x * w, lm.y * h])

    v1 = np.linalg.norm(pt(eye["v1_top"]) - pt(eye["v1_bot"]))
    v2 = np.linalg.norm(pt(eye["v2_top"]) - pt(eye["v2_bot"]))
    horiz = np.linalg.norm(pt(eye["h1"]) - pt(eye["h2"]))
    if horiz == 0:
        return 0.0
    return float((v1 + v2) / (2.0 * horiz))


def face_eye_score(path: Path) -> FaceEyeResult:
    """Detect faces in `path` and score eye-open state.

    No face -> neutral result (`score=1.0`) — most photos in a culling shoot
    are not portraits and should never be penalized for lacking a person.
    One or more faces, worst eye below `CLOSED_EYE_EAR_THRESHOLD` -> penalized.
    An unreadable/corrupt image also returns a neutral no-face result rather
    than raising, matching `scoring.py`/`quality_gate.py` convention of
    treating unreadable files as the gate's problem, not this signal's.
    """
    try:
        with Image.open(path) as img:
            rgb = np.array(img.convert("RGB"))
    except Exception:
        return FaceEyeResult(face_found=False)

    h, w = rgb.shape[:2]
    face_mesh = _get_face_mesh()
    result = face_mesh.process(rgb)
    if not result.multi_face_landmarks:
        return FaceEyeResult(face_found=False)

    worst_ears = []
    for face_landmarks in result.multi_face_landmarks:
        lm = face_landmarks.landmark
        left = _eye_aspect_ratio(lm, _LEFT_EYE, w, h)
        right = _eye_aspect_ratio(lm, _RIGHT_EYE, w, h)
        worst_ears.append(min(left, right))

    worst = min(worst_ears)
    closed = worst < CLOSED_EYE_EAR_THRESHOLD
    return FaceEyeResult(
        face_found=True,
        num_faces=len(worst_ears),
        min_ear=worst,
        eyes_closed=closed,
        score=CLOSED_EYE_PENALTY if closed else 1.0,
    )
