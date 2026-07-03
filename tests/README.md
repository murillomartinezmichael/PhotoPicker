# tests

Pytest suite for the PhotoPicker library.

## Running

All tests:
```bash
pytest
```

Quiet + fast summary:
```bash
pytest -q
```

With coverage:
```bash
pytest --cov=photopicker --cov-report=term-missing
```

A single file or single test:
```bash
pytest tests/test_scoring.py
pytest tests/test_scoring.py::test_ranks_sharp_higher
```

Only tests matching a keyword:
```bash
pytest -k dedup
```

## Layout

```
tests/
├── conftest.py             # shared fixtures (image sets, temp dirs, profiles)
├── test_batch.py           # batch pipeline end-to-end
├── test_cache.py           # decision cache read/write
├── test_classifier.py      # blur / noise / composition classifiers
├── test_cli.py             # click CLI surface
├── test_config_profile.py  # profile YAML loading
├── test_convert.py         # HEIC → JPEG conversion path
├── test_core.py            # scoring pipeline
├── test_dedup.py           # perceptual-hash dedup
├── test_exif.py            # EXIF read/normalize
├── test_profiles.py        # aries / big7 / default profile behaviors
├── test_quality_gate.py    # reject-below-threshold logic
└── test_scoring.py         # aggregate ranker
```

## What we test

Per `docs/TESTING_STANDARDS.md`:

- **Unit** — pure scoring, EXIF parsing, dedup math. No disk I/O beyond the
  fixture images.
- **Integration** — CLI end-to-end (`photopicker` on a fixture folder →
  ranked output), profile-driven runs.
- Fixtures live in `tests/fixtures/` when needed; keep them small and
  redistributable.

CI runs `pytest --cov=photopicker` in `.github/workflows/ci.yml`. Local
runs match CI exactly.

## Adding a new test

Follow the existing pattern — one `test_<module>.py` per production
module. Use fixtures from `conftest.py` for temp dirs and sample image
sets. Prefer parametrized tests over duplicated function bodies.
