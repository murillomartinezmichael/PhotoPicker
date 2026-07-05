# PhotoPicker STATUS

**One-liner:** Cull-first photo utility — offline dedup + quality gate + optional Claude Vision rerank, local web UI for K/X review, export with manifest. Reusable library API (`pick_photos`, `cull`) still shipped.

**Version:** 0.13.0 (in flight; v0.12 = `fef41dc` committed 2026-07-05).
**Ladder position:** **RUNG 1 — HARDEN** (started 2026-07-05).

## Ladder progress log

| Date | Rung | Note |
|---|---|---|
| 2026-07-05 | Cycle 1 complete | v0.11 shipped cull vertical (culler + webui + vision + CLI + 61 tests). |
| 2026-07-05 | Cycle 1 complete | v0.12 shipped sharpest-per-cluster + filter chips + resume + manifest + EXIF preservation tests (222/222 green). |
| 2026-07-05 | **RUNG 1 HARDEN** started | Money code (Vision) needs retry/backoff. Port-in-use fallback. Malformed session fallthrough. Output-folder permission errors. |

## Live surface

- `photopicker-cull FOLDER --top N` — main cull CLI (offline + optional AI rerank)
- `photopicker --folder FOLDER --profile <name>` — legacy themed picks (aries / big7 / default / aries-gallery)
- Web UI at `http://127.0.0.1:8765/` (K keep, X reject, U undo, arrows nav, Enter focus, F filter, E export, ? help)
- Python API: `from photopicker import pick_photos, cull, CullResult`

## What's green

- 222/222 pytest (was 199/201 pre-fix at session start; fixed 2 aries warmth tests + added 23 new)
- ruff `E/F/I/B/UP` clean
- CI runs on py 3.10 / 3.11 / 3.12
- End-to-end smoke: 20-photo cull → 5 keepers copied, web UI booted + shut down clean

## Perf baseline (`scripts/perf_1k.py`, 2026-07-05, local Windows py 3.10)

| n photos | top | total | twin-collapse | scoring | dedup | quality-gate |
|---:|---:|---:|---:|---:|---:|---:|
| 500 | 30 | **9.44s** | 12ms | 8.17s | 1.18s | 79ms |
| 1000 | 30 | **17.74s** | 44ms | 15.12s | 2.50s | 71ms |

Both well under the 10-minute finish-line gate. Vision rerank on top 100 keepers at ~1.5s per API call ≈ +150s in parallel (4 workers → ~40s wallclock), so a full 1000-photo run with `--prompt` still fits in ~1 minute total.

## What's not green yet

- No open-source-quality demo GIF or sample folder in `demo/` (Rung 5 in flight)
- Live cull-progress in the web UI is post-cull only; big folders show a blank screen for ~15s (Rung 6 candidate — SSE progress stream)
- `pillow_heif` `Image.Image.getdata` deprecation lands in Pillow 14 (2027-10); dedup.py:30 needs migration before then

## Cost per Vision run (as designed)

Sonnet 4.6 vision call ≈ ~2K input tokens (1568px JPEG) + ~50 output. At $3/M input + $15/M output → ~$0.007 per photo. Reranking 100 keepers ≈ $0.70. `--no-ai` stays $0.
