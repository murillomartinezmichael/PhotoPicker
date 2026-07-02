# CLAUDE.md — PhotoPicker

Project-specific guidance for Claude Code sessions.

## What this is

Reusable Python library + CLI that curates a "best N" set of photos from a folder. Built so each of Michael's project sites (Aries Outdoor Living, Big7 Construction, etc.) can drop in one profile and get a tight themed gallery. Ships built-in profiles `aries`, `big7`, and `default`.

## Stack

Python 3.10+ · Pillow + pillow-heif (HEIC) · OpenCV (sharpness) · Click (CLI) · CLIP via `transformers` (optional, for semantic labels via `[clip]` extra) · pytest · ruff

## Key files

- `photopicker/cli.py` — Click entrypoint (`photopicker` command)
- `photopicker/api.py` — `pick_photos(folder, profile_name)` — the public API
- `photopicker/profiles/` — one file per profile: `aries.py`, `big7.py`, `default.py`, plus `__init__.py` that registers them
- `photopicker/scoring.py` — composite quality (sharpness + exposure)
- `photopicker/classifier.py` — `StubClassifier` (default) + optional CLIP classifier
- `tests/` — 36 tests, 89% coverage; use `StubClassifier` (no torch needed) unless testing CLIP
- `pyproject.toml` — package metadata, `[clip]` and `[dev]` extras

## Rules

- **Public API is `pick_photos`** (not `pick`) — don't rename it
- **CLIP is opt-in** — core install must work with no torch; only `[clip]` pulls it
- **Add a profile = one file** — `photopicker/profiles/<site>.py` + register in `__init__.py` + tests. That's the whole contract. See `aries.py` as the reference
- **Every profile returns a `Selection`** (categorized dict of paths + summary) — do not invent new return shapes
- **Tests use `StubClassifier`** — do not pull torch into the test path
- **ruff + pytest must be clean** before merging. CI runs py 3.10/3.11/3.12
- **YAGNI** — no new scoring dimension without a profile that needs it

## Run locally

```bash
pip install -e ".[dev]"   # or [clip] to add semantic labels
ruff check .
pytest
```

## Key docs

- `BRD.md`, `TRD.md` (public API name + scoring dir names are corrected here), `RUNBOOK.md`, `ONBOARDING.md`
- `../ENGINEERING_STANDARDS.md` + `../docs/TESTING_STANDARDS.md` — repo-wide bar
