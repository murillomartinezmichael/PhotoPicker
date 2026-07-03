# PhotoPicker — Onboarding

**Audience:** new contributor on day 1.
**Goal:** ship a new site profile to `main` by day 3.
**Time:** ~2 hours per day, ~6 hours total — it's a small focused project, not a service.

PhotoPicker is small (~1k lines) and library-shaped. There is no service to run, no DB to migrate, no deploy to learn. Onboarding is "understand the scoring + classifier + profile pattern, then add a profile."

If you get stuck, the troubleshooting matrix in `RUNBOOK.md § 4` is the first place to look.

---

## Before day 1 — install these

| Tool | Why | Install |
|---|---|---|
| Python 3.11+, 3.11, or 3.12 | Project language. Don't use 3.13 — OpenCV wheel matrix isn't there yet. | https://python.org or `pyenv install 3.12` |
| Git | Source control | https://git-scm.com |
| VS Code (or any editor) | We standardize on VS Code with the Python + Ruff extensions | https://code.visualstudio.com |

System libs for HEIC support (only matters on Linux):
- Debian/Ubuntu: `sudo apt-get install libheif1`
- macOS: `brew install libheif`
- Windows: nothing to install — `pillow-heif` wheel includes the binary

---

## Day 1 — Run it, read it, scope it

### Goals
- Run PhotoPicker on a real folder of photos
- Read the four files that matter
- Trace one profile end-to-end

### Steps

1. **Read these in order, no skipping:**
   - `README.md` — what it does, CLI surface, profiles
   - `BRD.md` — why it exists (Aries + Big7 galleries had too many photos)
   - `TRD.md` — the architecture and stack rationale
   - `ENGINEERING_STANDARDS.md` (repo root) — how we write code here

2. **Clone and install:**
   ```bash
   git clone <repo>
   cd PhotoPicker
   ./build.sh           # or build.bat on Windows
   ```
   If it fails, RUNBOOK § 4 has the common ones.

3. **Run it on real photos.** Grab any folder of >10 photos (your own works fine):
   ```bash
   photopicker --folder ~/Pictures/test --profile default
   photopicker --folder ~/Pictures/test --profile default --output ./out
   ```
   Open `./out/` and confirm the picks look reasonable. `default` is pure quality (sharpness + exposure), no semantic labels.

4. **Read one profile top-to-bottom.** Open `photopicker/profiles/aries.py`. Trace it:
   - `STAGE_LABELS` — the CLIP prompts that classify each photo's construction stage
   - `select(paths, classifier)` — for each path: get stage probs, get a composite quality score
   - The greedy pick: best `before`, best `during`, best `after`, then top 6 of the rest
   - `register_profile(...)` at module load — this is how the CLI sees it

### You have succeeded today when
- [ ] You can describe in two sentences what PhotoPicker does
- [ ] You've run the CLI on a real folder and inspected the output
- [ ] You can explain in plain English how `aries.py` picks its 9 photos

---

## Day 2 — Read the rest of the code, run the tests

### Goals
- Understand every module
- Know the testing pattern (especially `StubClassifier`)
- Run all 36 tests green locally

### Steps

1. **Skim each module, write yourself one sentence per file:**
   - `photopicker/core.py` — `pick_photos()`, `discover_images()`, `PhotoPick` dataclass
   - `photopicker/cli.py` — Click wrapper around `pick_photos`
   - `photopicker/scoring.py` — sharpness (Laplacian variance) + exposure (histogram) → composite
   - `photopicker/classifier.py` — `Classifier` protocol, `ClipClassifier`, `StubClassifier`
   - `photopicker/exif.py` — EXIF helpers
   - `photopicker/profiles/registry.py` — `Profile` + `Selection` dataclasses, `register_profile()` / `get_profile()`
   - `photopicker/profiles/{aries,big7,default}.py` — the three built-ins

2. **Run the test suite:**
   ```bash
   pytest                       # ~2s
   pytest --cov=photopicker     # coverage report
   ```

3. **Read `tests/conftest.py`.** It builds tiny in-memory images so tests don't need real photo fixtures.

4. **Read `tests/test_profiles.py`.** Notice the pattern:
   - `StubClassifier` returns deterministic mock scores → no torch, no network, no CLIP weights
   - Each profile test asserts the *structure* of the selection (right keys, right counts), not exact pixel-level picks

5. **Run one test in isolation:**
   ```bash
   pytest tests/test_profiles.py::test_aries_picks_before_during_after -v
   ```

### You have succeeded today when
- [ ] You can name what every file in `photopicker/` does
- [ ] All 36 tests pass green
- [ ] You understand why we use `StubClassifier` for tests (no torch in CI)

---

## Day 3 — Add a new profile (your first PR)

### Goals
- Add a new site profile end-to-end
- Get it merged

This is the canonical contribution shape for PhotoPicker. Almost every change to this project is "add a profile" or "tweak the scoring."

### Steps

1. **Pick a fake site** (e.g. `acme` — "best 3 hero shots + best 6 detail shots"). For a real change, ask Michael — he'll point at the next site that needs one.

2. **Create the file:** `photopicker/profiles/acme.py`. Pattern:

   ```python
   """Acme — 3 heroes + 6 details."""
   from __future__ import annotations

   from pathlib import Path

   from ..classifier import Classifier
   from ..scoring import composite_score
   from .registry import Profile, Selection, register_profile

   HERO_COUNT = 3
   DETAIL_COUNT = 6


   def select(paths: list[Path], classifier: Classifier) -> Selection:
       scored = sorted(paths, key=composite_score, reverse=True)
       heroes = scored[:HERO_COUNT]
       details = scored[HERO_COUNT:HERO_COUNT + DETAIL_COUNT]
       return Selection(categorized={"heroes": heroes, "details": details})


   register_profile(Profile(name="acme", select=select))
   ```

3. **Register it.** Edit `photopicker/profiles/__init__.py`:

   ```python
   from . import acme, aries, big7, default
   ```
   And add `"acme"` to `__all__`. (This import is what runs `register_profile(...)` at startup.)

4. **Write a test.** Add to `tests/test_profiles.py`:

   ```python
   def test_acme_picks_3_heroes_and_6_details(stub_classifier, tmp_image_folder):
       paths = list(tmp_image_folder.iterdir())
       result = get_profile("acme").select(paths, stub_classifier)
       assert len(result.categorized["heroes"]) == 3
       assert len(result.categorized["details"]) == 6
   ```
   (Look at the existing tests for the actual fixture names.)

5. **Lint + test:**
   ```bash
   ruff check . --fix
   pytest
   ```

6. **Branch, commit, push, PR:**
   ```bash
   git checkout -b profile/acme
   git add photopicker/profiles/acme.py photopicker/profiles/__init__.py tests/test_profiles.py
   git commit -m "feat: add acme profile (3 heroes + 6 details)"
   git push -u origin profile/acme
   gh pr create
   ```

7. **CI must be green** (ruff + pytest on py3.10/3.11/3.12).

### You have succeeded today when
- [ ] A new profile is registered, tested, and ships through CI
- [ ] `photopicker --folder ./photos --profile <yours>` works after `pip install -e .`
- [ ] PR is merged to `main`

---

## The mental model

PhotoPicker is **three orthogonal pieces glued by a profile**:

1. **Quality score** (`scoring.py`) — sharpness + exposure → one number per photo. Cheap. Always runs.
2. **Semantic label** (`classifier.py`) — given a photo and a list of text prompts, returns probability per prompt. Real version is CLIP; tests use a stub. Optional per profile.
3. **Profile** (`profiles/<site>.py`) — pure function `(paths, classifier) -> Selection`. Decides what counts as "the right 9 photos for this site."

Data flow:

```
folder → discover_images() → [Path...] → profile.select() → Selection → CLI prints / copies
                                              │
                                              ├─ composite_score(path)        (always)
                                              └─ classifier.score(path, labels) (optional)
```

State: there is none. PhotoPicker is a pure pipeline. No DB, no cache (except HuggingFace's CLIP weight cache, which lives in `~/.cache/huggingface/`).

Why this shape: profiles change often, scoring + classification rarely. Keeping the profile as a one-file pure function means adding a new site is a contained PR with one test file diff.

---

## Glossary

| Term | Meaning |
|---|---|
| Profile | A registered function `(paths, classifier) -> Selection` that defines one site's curation rules |
| Selection | A dict-of-lists: `{category_name: [picked_paths]}` |
| Composite score | `scoring.composite_score(path)` — sharpness + exposure combined into one quality number |
| Stub classifier | A `Classifier` that returns deterministic mock probabilities. Used in all tests so CI doesn't need torch / CLIP weights |
| CLIP | OpenAI's image–text model. Optional dependency (`pip install -e ".[clip]"`). Powers semantic labels in `aries` and `big7` |
| HEIC | iPhone's default image format. Handled by `pillow-heif` |

---

## Troubleshooting

See `RUNBOOK.md § 4` for the matrix of common install / runtime failures. The frequent ones in practice:

| Symptom | Fix |
|---|---|
| `Unknown profile 'foo'` | Profile module not imported in `photopicker/profiles/__init__.py` |
| HEIC photos skipped silently | `pillow-heif` install failed; reinstall and check for libheif on Linux |
| `pip install ".[clip]"` takes forever | Normal — it's pulling ~2 GB of torch + CLIP weights. One-time |
| Tests pass locally, fail in CI on 3.10 | You used a 3.11+ syntax feature (`match`, `Self`, etc.). Either fix it or drop 3.10 from the matrix |

---

## After onboarding — leveling up

- Read `BRD.md` and `TRD.md` again now that you've seen the code — they'll land differently
- Skim `docs/adr/` if any ADRs have been written (currently scaffold only)
- Pair with Michael on the next downstream site that needs a profile — the trickiest part is naming what "the right gallery" looks like, not writing the code
- Try the `[clip]` extra and run `aries` on a real folder of construction photos — gives you intuition for what semantic labels can and can't do
