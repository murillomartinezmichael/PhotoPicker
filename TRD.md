# PhotoPicker — Technical Requirements

**Author:** Michael Martinez
**Last updated:** 2026-06-29
**Status:** Implemented v1
**Links:** [BRD](./BRD.md) · [RUNBOOK](./RUNBOOK.md) · [ONBOARDING](./ONBOARDING.md)

---

## 1. Summary

Reusable Python library + CLI that scores images and selects the best subset per a registered profile. Library is the source of truth; the CLI is a thin wrapper. Quality scoring composes sharpness (Laplacian variance via OpenCV) + exposure (Pillow histogram). Optional semantic labeling via CLIP; a `StubClassifier` keeps tests fast.

## 2. Non-functional requirements

| Category | Requirement |
|---|---|
| Cold-start (CLI w/o CLIP) | < 2s |
| Per-image scoring | < 100ms (no CLIP), < 1s (with CLIP on CPU) |
| Test coverage | > 80% (achieved 89%) |
| CI pass | < 5 min across py3.10/3.11/3.12 matrix |

## 3. Architecture

```
photopicker/
├── __init__.py            -- public API re-exports
├── core.py                -- pick_photos(), discover_images(), PhotoPick
├── cli.py                 -- Click CLI
├── scoring.py             -- sharpness (Laplacian) + exposure → composite_score()
├── classifier.py          -- Classifier protocol, ClipClassifier, StubClassifier
├── exif.py                -- EXIF helpers
└── profiles/
    ├── __init__.py        -- imports each profile module (triggers registration)
    ├── registry.py        -- Profile, Selection, register_profile / get_profile
    ├── aries.py           -- before/during/after + top 6 others
    ├── big7.py            -- repair/build buckets
    └── default.py         -- top 9 by composite quality
```

## 4. Stack choices

| Concern | Choice | Why |
|---|---|---|
| Language | Python 3.12+++ | ML ecosystem |
| Image I/O | Pillow + pillow-heif | iPhone uploads need HEIC |
| Sharpness | OpenCV Laplacian variance | Industry-standard cheap signal |
| Classification | CLIP via transformers | Strong zero-shot labels; optional |
| CLI | Click | Familiar, simple |
| Packaging | pyproject.toml + hatch | Modern Python packaging |

## 5. Public API

```python
from photopicker import pick_photos

result = pick_photos(folder="photos/", profile_name="aries")
print(result.summary())
for category, paths in result.selection.categorized.items():
    print(category, [p.name for p in paths])
```

```bash
photopicker --folder photos/ --profile aries --output curated/ [--json-out]
```

## 6. Testing

- 36 unit tests, 89% coverage
- StubClassifier for tests (no torch in CI)
- Matrix: 3.10 / 3.11 / 3.12 on GitHub Actions
- Coverage uploaded as artifact

## 7. Distribution

- Wheel built from CI on main branch
- Install: `pip install photopicker`
- Extras: `pip install photopicker[clip]` for CLIP support

## 8. Open questions

- Server mode (FastAPI wrapping the lib) — trigger: > 1 downstream site wants it
- Auto-orientation fix — trigger: misoriented images appear in galleries

## 9. Future work

- More site profiles (Aries v2 with explicit photo-type taxonomies)
- Optional auto-crop suggestion
- Web UI for human-in-the-loop refinement
