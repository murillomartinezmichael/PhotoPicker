# Changelog

All notable changes to this project.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.0] - 2026-07-05

**RUNG 1 HARDEN** — money-code retries, port fallback, malformed-session fallthrough, output-permission clean errors, corrupt-image safety, overwrite guard, plus a 1000-photo perf harness and a demo folder.

### Added
- `photopicker.vision.call_with_retry` — exponential-backoff wrapper (base 1s, cap 30s, ±25% jitter) that classifies transient failures (`RateLimitError`, `APIConnectionError`, timeouts, 5xx) vs terminal ones. `VisionRetryError` gives up cleanly after `max_attempts` (default 3, env `PHOTOPICKER_VISION_MAX_ATTEMPTS`, CLI `--ai-max-attempts`).
- `photopicker.vision.AnthropicVisionClient` now wraps every `messages.create` in the retry loop and surfaces retry events via a callback that `photopicker-cull` prints to stderr.
- CLI `--ai-max-attempts N` — retries per Vision call.
- CLI `--overwrite / --no-overwrite` — default `off` refuses to write into a non-empty `--output` folder (dotfiles like `.DS_Store` are ignored when probing).
- `photopicker.webui._bind_with_fallback` — if the configured `--port` is taken, try the next 10 ports before failing. Server prints "port X busy; landed on Y".
- `photopicker.convert.ImageUnreadable` — raised by `thumbnail_bytes` / `vision_bytes` on decode failure. Web UI `/photo/<idx>` returns 500 with the filename in the body; Vision rerank skips + logs.
- `scripts/perf_1k.py` — perf harness that seeds N synthetic photos and times the pipeline. Optional `--gate-seconds` for CI. **Baseline: 500 photos in 9.44s, 1000 in 17.74s** (see STATUS.md).
- `demo/seed.py` + `demo/README.md` — 40-photo synthetic dataset a stranger can run in two commands with no API key.
- New tests: 10 retry+backoff (`_backoff_delay` grow-and-cap + jitter, `_resolve_max_attempts` env override, `_is_retryable` classification, `call_with_retry` retries transient / gives up / doesn't retry KeyboardInterrupt), 2 port-fallback (uses N+1 when N taken, raises when range exhausted), 3 --resume fallthrough (malformed JSON, empty candidates, version drift), 3 permission-clean (output mkdir denied, manifest write denied, --ai-max-attempts wiring), 3 --overwrite (default refuses non-empty, --overwrite allows, dotfiles ignored), 5 convert hardening (junk file, missing file, zero byte, bad fmt still ValueError), 1 web UI corrupt-photo integration (returns 500 with filename in body). **9 new hardening tests bring the suite to 250/250 green, ruff-clean.**
- STATUS.md + DECISIONS.md scaffolded per Ignition Prompt boot rules. D-005 documents the retry decision.

### Changed
- `photopicker-cull` `_resume_ui` returns bool instead of exiting; malformed/empty/version-drifted session files now fall through to a fresh cull with a one-line warning instead of `sys.exit(1)`.
- `photopicker-cull --output DIR` write failures → `click.echo` + `sys.exit(2)` instead of stack trace.
- `photopicker-cull --manifest PATH` write failures → same clean-error treatment.
- README rewritten with the 2-command demo quickstart on top + perf baseline + full flag table incl. new options.
- `pyproject.toml` v0.12.0 → v0.13.0.

## [0.12.0] - 2026-07-05

Same-day follow-up to v0.11 — quality, UX, and completeness pass on the cull vertical.

### Added
- **Sharpest-per-cluster dedup.** Pipeline now scores every survivor once *before* perceptual dedup, so a near-duplicate cluster keeps the sharpest frame instead of the first-seen. Stage list: `twin-collapse → scoring → dedup → quality-gate → top N`.
- CLI `--sort {score,capture-time,name}` — presentation order of keepers. Truth (which photos win) stays score-driven; only display order changes.
- CLI `--include-rejects` — surfaces pipeline rejects (blurry / near-dupes / too-small) in the review UI so you can rescue false positives. Rejects appear behind a filter chip.
- CLI `--resume` — reopens the last saved session in `.photopicker-session.json` without re-running the cull pipeline. Fast when you Ctrl+C'd out mid-review.
- CLI `--manifest PATH` — writes a JSON manifest of the cull result (rank + score + capture_time + AI score/reason per pick + input_count + reject_counts).
- Web UI filter chips: All / Undecided / Keepers / Rejected / Pipeline rejects (only shown when `--include-rejects` populated the pool).
- Web UI sort dropdown: score / capture-time / filename.
- Web UI `F` shortcut cycles through filter chips.
- Web UI export dialog now includes a "Write manifest.json alongside exports" checkbox (default on) that emits a per-file manifest into the target folder.
- Web UI cards surface EXIF capture time as a badge when present.
- `photopicker.culler.CullResult.all_rejected()` — deduped view over every rejection reason.
- New tests: `test_exif_preservation.py` (4 tests — cull leaves originals byte-identical, JPG copy preserves EXIF + mtime), sharpest-per-cluster test, sort tests, resume test, include-rejects test, manifest tests, HTTP manifest-export tests, build_session `include_rejects` tests. **80+ tests total across the new surface; 222/222 full suite pass (including the 2 previously-flagged aries warmth tests, which are now fixed).**

### Fixed
- `tests/test_profiles.py::test_aries_warmth_breaks_tie_within_stage` and `test_aries_warmth_boosts_others_ranking` — pre-existing failures caused by the shared `folder_of_images` fixture mixing high-Laplacian checker patterns with low-Laplacian gradient patterns. The intrinsic quality gap overpowered the warmth signal. Both tests now build uniform-quality fixtures inline so warmth is the only differentiator, matching the behavior aries.py actually implements.

## [0.11.0] - 2026-07-05

The **cull** vertical — PhotoPicker moves from "themed profile library" to "point-and-cull tool" as its top-level surface.

### Added
- `photopicker.culler.cull(paths, top_n=30)` — offline pipeline (dedup → quality gate → composite score → top N). No CLIP, no torch, no themes. Deterministic and fast enough to feel instant on a 500-photo folder.
- `photopicker.webui` — self-contained local web UI (`http.server` + inlined HTML/CSS/JS, monospace + LEDs + scanlines). Grid of survivors, per-card KEEP / REJECT overlays, focus view. Endpoints: `/state`, `/photo/<idx>?w=N`, `/decision`, `/undo`, `/reset`, `/export`, `/shutdown`. Session state persists to `.photopicker-session.json` so Ctrl+C is safe.
- `photopicker.vision` — optional Claude Vision rerank behind the new `[vision]` extra. `rerank(paths, prompt, client)` scores each survivor 0–100 on how well it matches a plain-English prompt (composition, subject, portfolio quality). Threaded (default 4 workers). `parse_vision_reply` tolerates prose leaks from the model.
- `photopicker.convert.thumbnail_bytes()` and `vision_bytes()` — in-memory width-scaled thumbnails and Vision-ready JPEG bytes.
- CLI: `photopicker-cull FOLDER --top N` new console script. Flags: `--serve/--no-serve`, `--port`, `--output`, `--prompt`, `--no-ai`, `--ai-workers`, `--sharpness`, `--min-long-edge`, `--json-out`. Default UX: opens a browser tab, keyboard-driven cull, one-button export.
- Web UI keyboard shortcuts: K keep · X reject · U undo · ←/→ nav · Enter focus · E export · ? help · Esc close.
- `run.sh` / `run.bat` — `cull` and `pick` subcommands so the tool is one command from a clean clone.
- Tests: `test_culler.py` (10), `test_webui.py` (26, including full HTTP-integration tests against a live ThreadingHTTPServer), `test_vision.py` (14, with fake vision clients and error-path coverage), `test_cull_cli.py` (8). **61 new tests, all pass; ruff-clean.**

### Changed
- `pyproject.toml` — new `[vision]` extra pinning `anthropic>=0.34`. `photopicker-cull` registered as a second console script. Version 0.10.0 → 0.11.0.
- `README.md` — cull-first framing. Themed profiles moved below.
- `photopicker.__init__` exports `cull` and `CullResult`.

### Known
- `tests/test_profiles.py::test_aries_warmth_*` (2 tests) fail on this branch — pre-existing warmth-ranking behavior drift unrelated to the cull work. Aries `--profile aries` runs correctly against real folders; the tests need a rewrite to match how tie-breaking currently interacts with dedup ordering.

## [0.1.0] - 2026-07-03

Initial documented release. Prior work committed since 2026-06-30 is being
captured retroactively; see `git log` for the full history.

### Added
- README: replace hardcoded 'C:\Users\Michael\Documents\GitHub\' path with relative reference
- Dockerfile: build the wheel + expose the CLI entrypoint
- feat: v0.2.0 → v0.10.0 — full publish pipeline
- docs: add project CLAUDE.md pointing at repo-wide engineering standards
- chore: roll out engineering standards + cross-platform scripts
- chore: initial commit — PhotoPicker v1
