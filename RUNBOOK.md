# PhotoPicker — Runbook

**Last updated:** 2026-06-29
**Owner:** Michael Martinez
**Repo:** `C:\Users\Michael\Documents\GitHub\PhotoPicker`
**Shape:** Python library + CLI. **No service, no DB, no deploy, no on-call.** This runbook covers local use and packaging only.

---

## Quick reference

| Task | Command |
|---|---|
| Install (core only) | `pip install -e .` |
| Install with CLIP | `pip install -e ".[clip]"` |
| Install dev tools | `pip install -e ".[dev]"` |
| Run on a folder | `photopicker --folder ./photos --profile aries` |
| Run tests | `pytest` |
| Coverage | `pytest --cov=photopicker --cov-report=term-missing` |
| Lint | `ruff check .` |
| Build wheel | `python -m build` (or wait for CI on main) |

---

## 1. Local use

### 1.1 Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | 3.10, 3.11, or 3.12 | https://python.org or `pyenv install 3.12` |
| pip | bundled with Python | — |

That's it. There is no Docker, no DB, no message bus.

CLIP (optional): pulls `torch` + `transformers`, ~2 GB. Skip unless you're working on the `aries` or `big7` profile and want real semantic labels instead of `StubClassifier`.

### 1.2 First-time setup (clean clone)

```bash
git clone <repo>
cd PhotoPicker

# Unix / macOS
./build.sh

# Windows
build.bat
```

`build.sh` / `build.bat` will create a venv, install `.[dev]`, and verify `pytest` runs green.

### 1.3 Run the CLI

```bash
photopicker --folder ./photos --profile aries
photopicker --folder ./photos --profile big7 --output ./curated
photopicker --folder ./photos --profile default --json-out
```

Output goes to stdout. With `--output`, picks are also copied to subfolders by category (`before/`, `during/`, `after/`, `others/` for aries; `repair/`, `build/` for big7).

### 1.4 Use as a library

```python
from photopicker import pick_photos

pick = pick_photos(folder="./photos", profile_name="aries")
print(pick.summary())
```

For tests / CI, pass a `StubClassifier` so no torch is needed:

```python
from photopicker import pick_photos
from photopicker.classifier import StubClassifier

pick = pick_photos(folder="./photos", profile_name="aries", classifier=StubClassifier())
```

---

## 2. Tests

### 2.1 Run everything

```bash
pytest
```

36 tests, ~2s on a laptop. Coverage prints to terminal (configured in `pyproject.toml`).

### 2.2 Run one file / test

```bash
pytest tests/test_profiles.py
pytest tests/test_profiles.py::test_aries_picks_before_during_after
```

### 2.3 Coverage report (HTML)

```bash
pytest --cov=photopicker --cov-report=html
open htmlcov/index.html        # macOS
start htmlcov/index.html       # Windows
```

Current: **89%** line coverage. CI does not fail on coverage but should stay >80%.

### 2.4 Lint

```bash
ruff check .
ruff check . --fix             # auto-fix what's safe
```

CI is configured to fail on lint errors. Ruleset: `E F I B UP` (see `pyproject.toml`).

---

## 3. Packaging & release

### 3.1 Build a wheel locally

```bash
pip install build
python -m build
```

Outputs `dist/photopicker-<ver>-py3-none-any.whl`.

### 3.2 CI builds the wheel

`.github/workflows/ci.yml`:
1. Runs ruff + pytest on matrix (py3.10 / 3.11 / 3.12)
2. Uploads coverage as an artifact
3. On `main`: builds the wheel and uploads it as an artifact

There is no PyPI publish step right now — wheels are pulled from CI artifacts. If a downstream site needs it installed by pin, copy the wheel out of CI and `pip install` it.

### 3.3 Cut a release

1. Bump `version` in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Tag: `git tag -a v<X.Y.Z> -m "release notes" && git push --tags`
4. CI builds the wheel for the tag — pull from the workflow artifact

---

## 4. Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `pip install -e .` fails on `opencv-python-headless` build | Pre-built wheel missing for your Python version | Use 3.10/3.11/3.12 (the supported matrix). Don't run on 3.13 yet. |
| `pillow_heif` import error on Linux | Missing system libheif | `apt-get install libheif1` (Debian) / `brew install libheif` (mac) |
| `RuntimeError: CUDA out of memory` in `[clip]` mode | torch trying to use a GPU it can't fit | `pillow_heif` reads CPU-only by default; set `CUDA_VISIBLE_DEVICES=""` before running |
| First `[clip]` run hangs for minutes | Downloading CLIP weights (~600 MB) from HuggingFace | One-time. Subsequent runs use the local cache (`~/.cache/huggingface/`) |
| `Unknown profile 'foo'` | Profile not registered | Check `photopicker/profiles/__init__.py` imports your new profile module |
| Tests fail with HEIC errors | `pillow-heif` not installed | `pip install -e ".[dev]"` (it's in core deps) |
| `photopicker` command not found after install | Editable install missing from PATH | Re-activate the venv, or `python -m photopicker.cli` |

---

## 5. Profile authoring (operational)

Adding a new profile is a code change, not a config change. See ONBOARDING § "Add a profile" for the walk-through.

Quick recipe:
1. New file: `photopicker/profiles/<site>.py`
2. Define `select(paths, classifier) -> Selection`
3. Call `register_profile(Profile(name="<site>", select=select))` at module load
4. Import the module in `photopicker/profiles/__init__.py` so registration runs
5. Add tests in `tests/test_profiles.py` using `StubClassifier`
6. PR with `ruff check .` and `pytest` green

Reference: `photopicker/profiles/aries.py`.

---

## 6. Where things live

| Concern | File |
|---|---|
| Public API (`pick_photos`) | `photopicker/core.py` |
| CLI entry point | `photopicker/cli.py` |
| Profile registry | `photopicker/profiles/registry.py` |
| Built-in profiles | `photopicker/profiles/{aries,big7,default}.py` |
| Quality scoring (sharpness + exposure) | `photopicker/scoring.py` |
| CLIP / stub classifier | `photopicker/classifier.py` |
| EXIF helpers | `photopicker/exif.py` |
| Tests | `tests/test_*.py` (one file per module) |
| CI workflow | `.github/workflows/ci.yml` |

---

## 7. What this runbook deliberately omits

PhotoPicker is a library + CLI consumed inside other projects. It has **no** running service, so there is no:

- Production environment / deploy commands / rollback
- Database / migrations / seed data
- Healthcheck endpoint / dashboards / alerts
- On-call rotation / incident response
- Secret store / `.env` file

Downstream sites that *consume* PhotoPicker output (Aries, Big7) have their own runbooks for hosting and deploy. PhotoPicker just ships them a wheel.
