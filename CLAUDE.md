# CLAUDE.md — PhotoPicker

Project-specific guidance for Claude Code sessions.

## What this is

Reusable Python library + CLI that curates a "best N" set of photos from a folder. Built so each of Michael's project sites (Aries Outdoor Living, Big7 Construction, etc.) can drop in one profile and get a tight themed gallery. Ships built-in profiles `aries`, `big7`, and `default`.

## Stack

Python 3.10+ · Pillow + pillow-heif (HEIC) · OpenCV (sharpness) · Click (CLI) · CLIP via `transformers` (optional, for semantic labels via `[clip]` extra) · pytest · ruff

## Key files

- `photopicker/cli.py` — Click entrypoint (`photopicker` command)
- `photopicker/core.py` — `pick_photos(folder, profile_name)` — the public API
- `photopicker/profiles/` — one file per built-in profile: `aries.py`, `aries_gallery.py`, `big7.py`, `default.py`, `config_profile.py` (JSON-driven), plus `__init__.py` that registers them
- `photopicker/scoring.py` — composite quality (sharpness + exposure)
- `photopicker/quality_gate.py` — hard-reject filter (unreadable / too-small / blurry)
- `photopicker/dedup.py` — HEIC/JPG twin collapse + perceptual near-dup rejection
- `photopicker/exif.py` — `get_capture_time` for chronological ordering (used by `aries-gallery`)
- `photopicker/classifier.py` — `Classifier` Protocol + `classify_batch()` helper + `ClipClassifier` (batch-aware) + `StubClassifier`
- `photopicker/cache.py` — `CachingClassifier` wraps any classifier, batch- and per-image-aware, persists scores to JSON
- `photopicker/convert.py` — `copy_or_transcode()` / `transcode_to_jpg()` for the publish step; HEIC → JPG so browsers can render; `resolve_output_name()` for the `original` / `sequential` / `category-rank` rename schemes; `generate_thumbnails(fmt=...)` writes width-scaled JPGs or WebPs for `<picture>` srcset; `to_webp()` writes WebP siblings alongside every JPG
- `PhotoPick.to_manifest()` on `core.py` — structured dict for frontend integrations; CLI `--manifest PATH` writes it
- `tests/` — 75 tests, ~93% coverage; use `StubClassifier` (no torch needed) unless testing CLIP
- `pyproject.toml` — package metadata, `[clip]` and `[dev]` extras

## Rules

- **Public API is `pick_photos`** (not `pick`) — don't rename it
- **CLIP is opt-in** — core install must work with no torch; only `[clip]` pulls it
- **Add a profile = one file** — `photopicker/profiles/<site>.py` + register in `__init__.py` + tests. That's the whole contract. See `aries.py` as the reference
- **Every profile returns a `Selection`** (categorized dict of paths, plus optional `rejected` map of `{reason: [paths]}`) — do not invent new return shapes
- **Rejects are optional** — a profile that has no reject signal (e.g. `default`, `aries`) leaves `rejected` empty; `aries-gallery` populates it
- **Use `classify_batch(classifier, paths, labels)` from profiles**, not a per-image `classifier.score()` loop — one call amortizes CLIP over the whole folder
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
