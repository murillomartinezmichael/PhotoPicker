# PhotoPicker

ML-driven photo curator. Two verbs:

- **`photopicker-cull ./shoot --top 30`** — dead-simple culling. Point at a raw shoot folder, get the 30 best keepers in a local web UI. K to keep, X to reject, arrows to navigate, Enter for full-size, one button to export. Optional `--prompt "..."` for Claude Vision rerank on taste; `--no-ai` stays fully offline.
- **`photopicker --folder ./shoot --profile aries-gallery`** — themed curation. Site-specific profiles (aries / big7 / default / aries-gallery) produce categorized selections for portfolio galleries.

Built so each of Michael's project sites (Aries Outdoor Living, Big7 Construction, etc.) gets a tight, themed gallery, and any 500-photo folder becomes a curated 30-shot lineup in under 10 minutes.

## Stack

Python 3.10+ · Pillow + pillow-heif (HEIC) · OpenCV (sharpness) · Click (CLI) · stdlib `http.server` (web UI) · CLIP via `transformers` (optional themed labels) · Claude Vision via `anthropic` (optional composition rerank)

## Status

**v0.12.** Cull + web UI + Vision rerank + sharpest-per-cluster + filter chips + resume + manifest export. **222/222 tests green** · ruff-clean · CI on py3.10/3.11/3.12.

## Quick start — cull a shoot

```bash
# Point at a folder, get the 30 best in a local UI (offline; no API keys needed):
photopicker-cull ~/photos/aries_shoot_2026-07-05 --top 30

# Same, but rerank with Claude Vision on a prompt:
export ANTHROPIC_API_KEY=sk-ant-...
pip install "photopicker[vision]"
photopicker-cull ~/photos/aries_shoot_2026-07-05 --top 30 \
  --prompt "best deck photos for a portfolio"

# CLI-only, no UI, just copy the winners:
photopicker-cull ~/photos/shoot --top 30 --output ~/galleries/aries/ --no-serve
```

The UI:

- Grid of survivors, monospace + LEDs (light on the eyes, no photo-review app fatigue)
- **K** keep, **X** reject, **U** undo, **←/→** navigate, **Enter** full-size focus, **E** export, **?** help
- Session state persists to `.photopicker-session.json` — Ctrl+C safe
- Export button copies keepers into any folder you name; HEIC → JPG by default; originals untouched

### Cull flags

| Flag | Purpose |
|---|---|
| `--top N` | Number of keepers (default 30) |
| `--serve / --no-serve` | Open the web UI (default on unless `--output` is set) |
| `--port N` | Web UI port (default 8765) |
| `--output DIR` | Copy keepers here without opening UI |
| `--manifest PATH` | Write a JSON manifest of the cull (rank + score + capture_time + AI score) |
| `--prompt "..."` | Rerank survivors via Claude Vision on this prompt |
| `--no-ai` | Skip AI rerank even with `--prompt` |
| `--sort MODE` | Order keepers by `score` (default), `capture-time`, or `name` |
| `--include-rejects` | Also surface pipeline rejects in the UI so you can rescue false positives |
| `--resume` | Reopen the saved session in FOLDER without re-running the pipeline |
| `--sharpness N` | Reject frames below this Laplacian variance (default 60) |
| `--min-long-edge N` | Reject frames whose longer edge is < N pixels (default 800) |
| `--json-out` | Print the result as JSON instead of a summary |

## Install

From the repo root:

```bash
pip install -e .              # core (cull + profiles) — dep-light, no torch
pip install -e ".[clip]"      # add CLIP semantic labels for themed profiles
pip install -e ".[vision]"    # add Claude Vision rerank for `--prompt`
pip install -e ".[dev]"       # pytest + coverage + ruff
```

`build.sh` / `build.bat` set the core install up from a clean clone. `run.sh cull ./shoot` is the one-liner operator target.

## Themed profiles (`photopicker` command)

| Profile | What it picks |
|---|---|
| `aries` | 1 before + 1 during + 1 after + top 6 others (CLIP labels the construction stage) |
| `aries-gallery` | **Full-batch curation** for portfolio detail pages: twin dedup → perceptual dedup → quality gate → CLIP phase classify → per-phase ranked lists (cap 8 each). Use this when handing raw client folders (mixed HEIC/JPG, some blurry, some near-dupes) straight to a portfolio site. |
| `big7` | splits photos into `repair` / `build` buckets, top 6 each |
| `default` | top 9 by composite quality (sharpness + exposure) |

## CLI

```bash
photopicker --folder ./photos --profile aries
photopicker --folder ./photos --profile big7 --output ./curated
photopicker --folder ./photos --profile default --json-out
```

| Flag | Purpose |
|---|---|
| `--folder, -f` | Input folder (required) |
| `--profile, -p` | One of `aries`, `big7`, `default` (required) |
| `--output, -o` | If set, copies picks into subfolders by category |
| `--json-out` | Emit the selection as JSON instead of human summary |

## Programmatic use

```python
from photopicker import pick_photos

pick = pick_photos(folder="./photos", profile_name="aries")
print(pick.summary())
for category, paths in pick.selection.categorized.items():
    print(category, [p.name for p in paths])
```

## Add a new profile

1. Create `photopicker/profiles/<site>.py`
2. Implement `select(paths, classifier) -> Selection`
3. Register at module load: `register_profile(Profile(name="<site>", select=select))`
4. Add it to `photopicker/profiles/__init__.py` imports
5. Write tests in `tests/test_profiles.py` (use the `StubClassifier` — no torch needed)

See `photopicker/profiles/aries.py` as the reference.

## Dev quick-start

```bash
pip install -e ".[dev]"
ruff check .
pytest                        # 132 tests, ~12s
pytest --cov=photopicker
```

## Why this exists

Michael's project sites currently show too many photos. PhotoPicker centralizes "pick the best N" logic so each site gets a tight, themed gallery, and adding a new site is one file + one register call.

<!-- standards-block-v1 -->
## Standards & docs

This project follows the cross-repo engineering standards. See the repo-root docs (one level up from this project):

| Doc | Purpose |
|---|---|
| `ENGINEERING_STANDARDS.md` | Principles + code quality + stack picking + Definition of Done |
| `docs/TESTING_STANDARDS.md` | Test pyramid, coverage gates |
| `docs/API_STANDARDS.md` | REST + Swagger + Postman conventions |
| `docs/OBSERVABILITY_STANDARDS.md` | Logs / metrics / traces / health / alerts |
| `docs/SECURITY_STANDARDS.md` | OWASP top 10, auth, secrets, supply chain |
| `docs/DATABASE_STANDARDS.md` | Schema, migrations, indexing |
| `docs/HOSTING_STANDARDS.md` | Hosting picks + cost ladder |
| `docs/MICROSERVICES_STANDARDS.md` | When to split, contracts, fitness function |

Project-specific docs live in this repo at the root: `BRD.md` · `TRD.md` · `RUNBOOK.md` · `ONBOARDING.md` · `CHANGELOG.md` · `CONTRIBUTING.md` · `SECURITY.md`.

ADRs live in `docs/adr/`. Postmortems live in `docs/postmortems/`.
