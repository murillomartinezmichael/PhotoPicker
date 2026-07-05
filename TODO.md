# PhotoPicker TODO

## Shipped 2026-07-05 — v0.12 follow-up (same day)

- **Sharpest-per-cluster dedup.** Pipeline scores every survivor once *before* perceptual dedup so near-duplicate clusters keep the sharpest instead of first-seen.
- CLI: `--sort`, `--include-rejects`, `--resume`, `--manifest` shipped with tests.
- Web UI: filter chips (All / Undecided / Keepers / Rejected / Pipeline rejects), sort dropdown, `F` cycle, capture-time card badges, export manifest.json checkbox.
- **Fixed the 2 pre-existing aries warmth test failures** with uniform-quality fixtures.
- New `test_exif_preservation.py` (4 tests) — originals byte-identical after cull, EXIF/mtime survive copy.
- **Full suite 222/222 green, ruff-clean.** Version 0.11.0 → 0.12.0.

## Shipped 2026-07-05 — v0.11 cull vertical

- `photopicker-cull FOLDER --top N` new console script — offline pipeline (dedup + quality gate + composite score → top N).
- Local web UI at `http://127.0.0.1:8765` — grid + K/X keyboard + focus view + export dialog. Session persisted to `.photopicker-session.json`.
- Optional Claude Vision rerank via `--prompt "..."` — parallelized 4-worker `ThreadPoolExecutor`. Guarded by `[vision]` extra (`anthropic>=0.34`). `--no-ai` stays offline.
- 61 new tests pass (culler, webui, vision, cull_cli). Ruff-clean.
- `run.sh`/`run.bat` `cull` + `pick` subcommands.
- README rewritten cull-first. CHANGELOG entry landed at v0.11.0.
- End-to-end smoke: culled 20 photos to top 5 with copy to output; UI booted on port 18766, `/health`, `/state`, `/photo/0`, `/` all returned real data; shutdown clean.

## Next action (60-second cold-open)

1. Michael runs:
   ```bash
   cd C:/Users/Michael/Documents/GitHub/PhotoPicker
   git add -A
   git commit -m "feat(cull): photopicker-cull + web UI + Claude Vision rerank (v0.11)"
   git push origin main
   ```
2. Then the definition-of-done smoke: point `photopicker-cull` at a real 500-photo shoot folder (Aries or Big7). Target: 500 → 30 in under 10 min including click-through.
3. If step 2 passes: record a 60-second demo video for the portfolio piece + the TikTok / repo header.

## Parked

- **2 pre-existing test failures** — `tests/test_profiles.py::test_aries_warmth_breaks_tie_within_stage` and `test_aries_warmth_boosts_others_ranking`. Unrelated to cull work; aries warmth-ranking tests need to catch up to how the current `aries.py` interacts with dedup ordering. Not blocking cull ship.
- **Dedup deprecation warning** — `Pillow 14` will remove `Image.Image.getdata` used in `photopicker/dedup.py:30`. Migrate to `get_flattened_data` before 2027-10-15.
- **`ANTHROPIC_API_KEY` gate** — `--prompt` requires the env var; document in RUNBOOK the exact command Michael runs to set it (`$env:ANTHROPIC_API_KEY = "sk-ant-..."` in PowerShell).
- **Open-source polish** — if this becomes a public repo: add a `demo/` folder with 20 CC0 photos, a `docs/demo.gif` of the K/X flow, and a licence header on the widget HTML.
