# PhotoPicker — Business Requirements

**Author:** Michael Martinez
**Last updated:** 2026-06-29
**Status:** Implemented v1 (132 tests, 94% coverage, ruff-clean, CI green)
**Stakeholders:** Michael, downstream sites (AriesOutdoorLiving, Big7Construction)

---

## 1. Problem

Michael's project sites (Aries, Big7, etc.) show too many photos — long undifferentiated grids that bury the strongest images. Curation by hand:
- Doesn't scale across many sites
- Is subjective and inconsistent across galleries
- Reuses the same eye + has no quality signal

A central tool that takes a folder of images and outputs the curated lineup — per site profile — solves this once and is reusable everywhere.

## 2. Who has this problem

### Primary
- **Michael** building gallery sections on his client sites
- **Downstream sites** consuming PhotoPicker output

### Anti-persona
- Not for consumer photo album curation
- Not for video curation

## 3. Success criteria

| # | Metric | Target |
|---|---|---|
| 1 | Per-site profile picks a tight, themed gallery | ✅ aries/big7/default |
| 2 | Test coverage | > 80% ✅ (94%) |
| 3 | Distributable via pip wheel | ✅ from CI on main |
| 4 | New profile = one file + one register call | ✅ |
| 5 | Lint-clean (ruff) | ✅ green |

## 4. Scope

### In scope
- CLI: `photopicker --folder <dir> --profile <aries|big7|default>`
- Built-in profiles: `aries`, `big7`, `default`
- Quality scoring: sharpness + exposure (Pillow + OpenCV)
- Optional CLIP semantic labels via `transformers`
- StubClassifier for tests — no torch in CI
- pip-installable wheel

### Profile behavior
- `aries`: 1 before + 1 during + 1 after + top 6 others (CLIP labels match construction stages)
- `big7`: splits into `repair` / `build` buckets, top 6 each
- `default`: top 9 by composite quality

### Out of scope (v1)
- Web UI
- Cloud-hosted API
- Video frame selection

### Maybe later
- More profiles (Aries v2 with explicit photo-type taxonomies)
- Server mode (FastAPI wrapping the lib)
- Auto-crop / orientation correction

## 5. User stories

1. As Michael building Aries gallery, I run the CLI and get 9 perfectly-chosen images.
2. As a downstream site, I depend on the wheel and call the API directly.
3. As Michael adding a new site, I write `profiles/newsite.py` with one function, register it, done.

## 6. Constraints

- Python 3.12+++
- CLIP is optional (large dep) — pure-Pillow path works without it
- CI must pass without GPU / torch

## 7. Risks

| Risk | Mitigation |
|---|---|
| CLIP bloats install | Optional via `extras_require` |
| Quality scoring fails on edge cases | Default sort by composite, never error |
| Profile drift across sites | Profile is code → reviewed in PRs |

## 8. Dependencies

- Pillow, pillow-heif (HEIC)
- OpenCV (sharpness)
- Click (CLI)
- Optional: transformers + torch (CLIP)


<!-- AI-HUB-SYNC:START -->
## AI Product Research Update - 2026-07-09

Source of product truth: ..\AI_HUB.md.

**Lane:** photo culling for client sites

**Design decision:** CLI/library is right. If a UI ever appears, it should be a contact-sheet review, not a full photo manager.

**Product direction:** Document profiles for Big7 and Aries V2, keep tests green, and integrate only at asset intake points.

**Scope boundary:** Shared utility; prevent duplicate photo pickers.

**Acceptance evidence:** pytest; profile fixture tests; CI.
<!-- AI-HUB-SYNC:END -->
