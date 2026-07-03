# PhotoPicker

ML-driven photo curator for project galleries. Point it at a folder, name a site profile, get back the curated lineup. Built so each of Michael's project sites (Aries Outdoor Living, Big7 Construction, etc.) gets a tight, themed gallery instead of an endless grid.

## Stack

Python 3.10+ · Pillow + pillow-heif (HEIC) · OpenCV (sharpness) · Click (CLI) · CLIP via `transformers` (optional, for semantic labels)

## Status

**v1 implemented.** 36 unit tests · 89% coverage · ruff-clean · CI green on py3.10/3.11/3.12.

## Install

From the repo root:

```bash
pip install -e .              # core only — StubClassifier, no CLIP
pip install -e ".[clip]"      # add CLIP semantic labels (pulls torch + transformers)
pip install -e ".[dev]"       # pytest + coverage + ruff
```

`build.sh` / `build.bat` will set this up from a clean clone.

## Built-in profiles

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
pytest                        # 36 tests, ~2s
pytest --cov=photopicker
```

## Why this exists

Michael's project sites currently show too many photos. PhotoPicker centralizes "pick the best N" logic so each site gets a tight, themed gallery, and adding a new site is one file + one register call.

<!-- standards-block-v1 -->
## Standards & docs

This project follows the cross-repo engineering standards. See top-level docs at `C:\Users\Michael\Documents\GitHub\`:

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
