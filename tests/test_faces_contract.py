"""Contract tests for the optional `faces` extra — these ALWAYS run.

Why this file exists
--------------------
`tests/test_faces.py` opens with::

    mp_pytest = pytest.importorskip("mediapipe", reason="requires photopicker[faces]")

and CI installs ``pip install -e ".[dev]"`` — never ``[faces]``. So every face
test silently skipped, and the suite still reported green. On 2026-08-08
Dependabot PR #6 (mediapipe 0.10.21 -> 1.0.0) rode that blind spot to five
green check marks. Reproduced locally in ``python:3.11-slim``::

    $ pip install -e '.[dev]' && pip install 'mediapipe==1.0.0'
    $ python -c "import mediapipe as mp; print(hasattr(mp, 'solutions'))"
    False
    $ pytest tests/test_faces.py
    E  AttributeError: module 'mediapipe' has no attribute 'solutions'
       photopicker/faces.py:74: AttributeError
    5 failed, 2 passed

mediapipe 1.0.0 removes ``mp.solutions`` outright. `photopicker/faces.py`
calls ``mp.solutions.face_mesh.FaceMesh(...)``, so the bump breaks face
detection completely. It would also break the offline guarantee: the
replacement Tasks API downloads model assets at runtime, where 0.10.21 bundles
the model in the wheel.

The tests below need no mediapipe and therefore never skip. They are what
turns that PR red. The companion `faces` CI job installs the extra for real
and runs `tests/test_faces.py`, so the behaviour is covered too; this file is
the cheap always-on backstop.

Stdlib only, and no `tomllib` — the CI matrix includes 3.10, where `tomllib`
does not exist and `tomli` is not a dependency.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
FACES_MODULE = REPO_ROOT / "photopicker" / "faces.py"
FACES_TESTS = REPO_ROOT / "tests" / "test_faces.py"

# The last mediapipe release that still ships the legacy `solutions` API.
LAST_SOLUTIONS_RELEASE = "0.10.21"

# The call site that makes the pin load-bearing.
LEGACY_API_CALL = "mp.solutions.face_mesh.FaceMesh"


def _mediapipe_requirement() -> str:
    """The single mediapipe requirement string inside the [faces] extra."""
    text = PYPROJECT.read_text(encoding="utf-8")
    block = re.search(r"^faces\s*=\s*\[(.*?)^\]", text, re.S | re.M)
    assert block, "pyproject.toml lost its [faces] optional-dependency group"
    reqs = re.findall(r"""["']\s*(mediapipe[^"']*)["']""", block.group(1))
    assert len(reqs) == 1, f"expected exactly one mediapipe requirement, got {reqs!r}"
    return reqs[0].strip()


def test_mediapipe_is_pinned_to_the_last_solutions_release() -> None:
    """The `faces` extra must stay pinned at the last mediapipe with `solutions`.

    This is the guard that fails a Dependabot bump. `pytest.importorskip` in
    tests/test_faces.py cannot fail it -- CI does not install the extra, so
    those tests never run and the bump looks green.
    """
    req = _mediapipe_requirement()
    assert req == f"mediapipe=={LAST_SOLUTIONS_RELEASE}", (
        f"the [faces] extra must stay pinned to "
        f"mediapipe=={LAST_SOLUTIONS_RELEASE}, but pyproject.toml says {req!r}.\n"
        f"\n"
        f"mediapipe 0.10.22+ removed the legacy `mediapipe.solutions` API "
        f"(1.0.0 drops the `solutions` attribute entirely), and "
        f"photopicker/faces.py calls {LEGACY_API_CALL}(...). Bumping breaks "
        f"face/closed-eye detection outright.\n"
        f"\n"
        f"It also breaks the offline guarantee: the replacement Tasks API "
        f"downloads model assets at runtime, where 0.10.21 bundles the model "
        f"in the wheel.\n"
        f"\n"
        f"Do not relax this pin on its own. Port photopicker/faces.py to the "
        f"Tasks API first (including how the model asset is vendored for "
        f"offline use), update this test in the same change, and confirm the "
        f"`faces` CI job passes against the new version."
    )


def test_faces_module_still_uses_the_legacy_api() -> None:
    """Pin and call site must move together.

    If someone ports faces.py to the Tasks API but forgets the pin, or lifts
    the pin but leaves the old call, these two tests disagree loudly instead of
    shipping a broken optional feature.
    """
    src = FACES_MODULE.read_text(encoding="utf-8")
    assert LEGACY_API_CALL in src, (
        f"photopicker/faces.py no longer calls {LEGACY_API_CALL}. If it was "
        f"ported to the mediapipe Tasks API, update LAST_SOLUTIONS_RELEASE, "
        f"the pin in pyproject.toml's [faces] extra, and this test in the "
        f"same change."
    )


def test_faces_tests_are_gated_on_the_extra() -> None:
    """tests/test_faces.py must stay guarded, so the core suite needs no mediapipe.

    Kept explicit because removing the guard would turn the default
    `pip install -e ".[dev]"` run red for every contributor, and the obvious
    "fix" would be to move mediapipe into `dev` -- exactly the heavy-dependency
    coupling the optional-extra pattern exists to avoid.
    """
    src = FACES_TESTS.read_text(encoding="utf-8")
    assert 'importorskip("mediapipe"' in src, (
        "tests/test_faces.py must keep its pytest.importorskip('mediapipe') "
        "guard so the core suite stays installable without the faces extra"
    )


def test_ci_runs_the_faces_tests_for_real() -> None:
    """CI must have a job that installs the extra and actually runs the tests.

    Without it, `[faces]` is exercised nowhere and the only thing standing
    between a bad bump and a green merge is the version pin above -- which is
    a proxy, not the behaviour.
    """
    ci = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert re.search(r'^\s{2}faces:', ci, re.M), (
        ".github/workflows/ci.yml has no `faces` job -- nothing installs the "
        "faces extra, so tests/test_faces.py never runs in CI"
    )
    assert "[dev,faces]" in ci, (
        "the `faces` CI job must install the extra "
        '(pip install -e ".[dev,faces]"), otherwise its face tests skip and '
        "report green"
    )


def test_installed_mediapipe_matches_the_pin() -> None:
    """When mediapipe IS present, its version must match the pin.

    Deliberately not a skipif: in the default `[dev]` environment it falls
    through to a real assertion about the pin's shape, so it never becomes
    another silent skip. In the `faces` CI job the extra is installed and this
    catches a resolver that quietly landed a different version than
    pyproject.toml asked for.
    """
    try:
        import mediapipe
    except Exception:
        # No extra installed: nothing to cross-check, so assert the pin is at
        # least well-formed. This branch still does real work.
        assert _mediapipe_requirement().startswith("mediapipe==")
        return

    installed = getattr(mediapipe, "__version__", None)
    assert installed == LAST_SOLUTIONS_RELEASE, (
        f"the faces extra pins mediapipe=={LAST_SOLUTIONS_RELEASE} but the "
        f"installed version is {installed!r}. photopicker/faces.py needs the "
        f"legacy `solutions` API, which 0.10.22+ removed."
    )
    assert hasattr(mediapipe, "solutions"), (
        f"installed mediapipe {installed} has no `solutions` attribute -- "
        f"photopicker/faces.py cannot call {LEGACY_API_CALL} against it"
    )
