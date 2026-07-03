# Changelog

All notable changes to this project are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

---

## [0.10.0] — 2026-07-03

### Added
- `photopicker.convert.to_webp(source, dest, quality)` — mirror of `transcode_to_jpg` writing WebP (encoder method=6 for best compression). Default quality 82 ≈ JPG 92 by eye but 25-35% smaller.
- `generate_thumbnails(..., fmt="webp")` — the thumbnail helper now takes a `fmt` kwarg (`"jpg"` or `"webp"`), so one function powers both srcset formats. Unknown `fmt` raises `ValueError`.
- CLI `--webp/--no-webp` flag — when set alongside `--output`, every pick spawns a `.webp` sibling of the main file plus (if `--thumbnails` is on) matching `-Nw.webp` siblings.
- CLI `--webp-quality N` flag (default 82).
- `PhotoPick.to_manifest(webp_paths=..., thumbnails_webp=...)` — new optional maps. When populated, picks carry `output_webp`, `output_webp_filename`, and `thumbnails_webp` so a `<picture>` block can offer `<source type="image/webp">` first with `<source type="image/jpeg">` fallback.
- Copy log adds a WebP counter, e.g. `"Copied 9 photos to ~/site/img (9 transcoded to JPG, renamed via category-rank, 18 thumbnails, 27 webp)"`.
- 8 new tests: 2 for `TestGenerateThumbnails` (webp format + unknown-fmt raise), 3 for `TestToWebp` (valid output, parent dirs, HEIC-extension input), 2 CLI end-to-end (with and without thumbnails), 2 core manifest tests (webp fields thread through, absent when not provided).

### Changed
- `generate_thumbnails` signature gains an optional `fmt` kwarg. Default `"jpg"` preserves existing behavior.

---

## [0.9.0] — 2026-07-03

### Added
- `photopicker.convert.generate_thumbnails(source, dest_dir, base_stem, widths, quality)` — emits `<base_stem>-<width>w.jpg` files scaled by the requested widths. Aspect ratio preserved, upscaling skipped, duplicate widths deduplicated. Returns a `{width: Path}` map.
- CLI `--thumbnails 400,800,1200` flag — comma-separated widths, default off. When set alongside `--output`, each pick spawns thumbnail siblings in the same category folder.
- `PhotoPick.to_manifest(thumbnails=...)` — optional `{source: {width: thumb_path}}` map. When provided, each pick carries a `thumbnails` field of stringified-width → filename that drops straight into a `<picture>` srcset.
- Copy log reports the thumbnail count, e.g. `"Copied 24 photos to ~/site/img (12 transcoded to JPG, renamed via category-rank, 72 thumbnails)"`.
- Two invalid-input CLI paths (`--thumbnails not-a-number`, non-positive widths) exit with a clear error.
- 8 new tests: 6 in `TestGenerateThumbnails` (per-width output, aspect ratio, upscale skip, empty input, dest-dir creation, dedup); 2 CLI end-to-end (srcset siblings + manifest map, invalid input); 2 manifest core tests (map survives serialization, field absent when not provided).

---

## [0.8.0] — 2026-07-03

### Added
- `photopicker.convert.resolve_output_name()` — computes the target filename for a picked photo given `(category, rank_in_category, global_rank, total_picks, scheme, convert_heic)`. Extension follows the transcoded output so naming and bytes stay in sync.
- `RENAME_SCHEMES` constant exposing the three valid schemes.
- CLI `--rename-scheme {original,sequential,category-rank}` flag (default `original`):
  - `original` keeps the source filename (with the extension swap when HEIC transcodes).
  - `sequential` numbers globally: `01.jpg`, `02.jpg`, ... with padding sized to the pick count.
  - `category-rank` emits `before-01.jpg`, `during-03.jpg`, ... — anonymizes client-facing galleries by dropping iPhone `IMG_NNNN` names.
- `copy_or_transcode(..., target_name=...)` — new kwarg so callers can override the derived filename (used by the CLI to pass through the rename scheme).
- Copy log now reports the rename step, e.g. `"Copied 24 photos to ~/site/img (7 transcoded to JPG, renamed via category-rank)"`.
- 11 new tests: 2 for `copy_or_transcode` target_name, 9 for `resolve_output_name` covering all three schemes + edge cases + unknown-scheme raise, 2 CLI end-to-end tests (category-rank anonymizes IMG_* filenames, sequential numbers globally).

---

## [0.7.0] — 2026-07-03

### Added
- `photopicker.convert` — new module with `transcode_to_jpg()` and `copy_or_transcode()`. HEIC/HEIF sources get transcoded to JPG (quality 92 default); other formats copy byte-for-byte preserving mtime/EXIF.
- CLI `--convert-heic/--no-convert-heic` flag (default **on** when `--output` is set) — closes the "iPhone → website" publish gap since browsers can't render HEIC.
- CLI `--jpg-quality N` flag (default 92) — knob for the transcode.
- `PhotoPick.to_manifest(output_paths=...)` — optional map of source → resolved output path. When provided, each pick gets `output_path` and `output_filename` fields pointing at the (possibly transcoded) file the frontend should actually reference. The CLI populates this automatically when `--output` is set.
- Copy log now reports transcode counts, e.g. `"Copied 24 photos to ~/site/img (7 transcoded to JPG)"`.
- 11 new tests: 8 in `tests/test_convert.py` (transcode + dispatch matrix), 2 in `tests/test_core.py` (manifest output_paths), 2 CLI end-to-end (HEIC → JPG happy path + `--no-convert-heic` opt-out).

---

## [0.6.0] — 2026-07-03

### Added
- `photopicker.build_from_config(cfg: dict) -> Profile` — build a full-pipeline profile from a plain dict. Runs the same dedup → gate → CLIP → per-phase rank → chronological pipeline as `aries-gallery` but reads phase labels, caps, and quality-gate/dedup thresholds from the config. Onboards a new project in one JSON file, no Python.
- `photopicker.ConfigError` — raised for malformed configs (missing `phases`, empty phase descriptions, etc.).
- CLI `--config PATH` flag — reads a JSON config, registers the built profile, and picks. When `--config` is set, `--profile` is optional (defaults to the config's `name`).
- 12 new tests (`tests/test_config_profile.py`) covering profile construction, per-phase cap, chronological on/off, reject reporting, default name fallback, all three validation errors, CLI end-to-end, CLI failure modes, and dynamic registration.

### Changed
- `--profile` is no longer strictly required at the CLI. If `--config` is set, the profile name comes from the config file. If neither is set, the CLI exits with a clear error.

---

## [0.5.0] — 2026-07-03

### Added
- `photopicker.classify_batch(classifier, paths, labels)` — module-level helper that dispatches to `classifier.score_batch()` when available, falls back to per-image `score()` otherwise. Profiles use this so any classifier — batch-capable or not — plugs in transparently.
- `ClipClassifier.score_batch()` — real batch CLIP inference. One forward pass per `batch_size` (default 32) images instead of one per image. On a 200-photo folder this is the difference between "make coffee" and "instantaneous."
- `ClipClassifier.__init__(batch_size=...)` — power-user knob for GPU/CPU memory tuning.
- `CachingClassifier.score_batch()` — serves cache hits without touching inner, batches misses to `inner.score_batch()` for maximum speed on re-runs with new photos in the folder.
- `StubClassifier.score_batch()` + `batch_calls` recorder for tests.
- 7 new tests (`tests/test_batch.py`) covering: batch dispatch when available, per-image fallback, hit/miss split in caching classifier, cross-instance persistence via batch path, profile output identical whether classifier is batch-capable or not.

### Changed
- `aries`, `aries-gallery`, and `big7` profiles now classify via `classify_batch` instead of a per-image loop. Behavior is byte-identical; real CLIP runs collapse into batches.

---

## [0.4.0] — 2026-07-03

### Added
- `PhotoPick.to_manifest()` — structured dict with `profile`, `source`, `generated_at` (UTC ISO), a `picks` list (one entry per selected photo with `category`, `rank`, `filename`, `path`, `capture_time`, `dimensions`), and `reject_counts`. Reject paths are intentionally omitted so manifests can ship into web builds.
- CLI `--manifest PATH` flag — writes the manifest JSON to disk. Combines with `--output` (files) and `--json-out` (stdout) as complementary artifacts.
- 5 new tests covering manifest shape, per-category rank reset, EXIF serialization, reject-count propagation, and CLI end-to-end write.

---

## [0.3.0] — 2026-07-03

### Added
- `photopicker.CachingClassifier` — wraps any `Classifier` and persists scores to a JSON file. Key is `(abs path, mtime_ns, size, sorted labels)`, so file edits or label-set changes force a re-score. Turns gallery-tuning re-runs from CLIP-bound to near-instant.
- CLI `--cache PATH` flag — opt-in cache for the CLIP classifier. First run populates the file; subsequent runs skip CLIP for unchanged photos.
- 8 new tests (`tests/test_cache.py`) covering miss/hit, cross-instance persistence, mtime invalidation, label-set isolation, order-independence, corrupt-file recovery, and stats.

---

## [0.2.0] — 2026-07-03

### Added
- `photopicker.dedup` — HEIC/JPG twin collapse + perceptual (average-hash) near-duplicate rejection. Public API: `dedup_all()`, `collapse_heic_jpg_twins()`, `dedup_perceptual()`, `average_hash()`, `hamming_distance()`.
- `photopicker.quality_gate` — hard-reject filter for unreadable / too-small / blurry frames. Public API: `check()`, `filter_usable()`, `GateResult`.
- New profile: `aries-gallery` — full-batch curation for portfolio detail pages. Pipeline: twin dedup → perceptual dedup → quality gate → CLIP phase classification → per-phase ranked lists (default cap 8). Distinct from the existing `aries` profile which picks a tight 9-photo hero set.
- `aries-gallery` sorts each phase chronologically via EXIF capture time so galleries read as a storytelling timeline (before → during → after unfolds oldest-first within each phase). Photos without EXIF sort last in filename order.
- `Selection.rejected` — a `{reason: [paths]}` map so callers can report what was cut (`duplicates`, `unreadable`, `too_small`, `blurry`). `Selection.reject_counts()` returns a compact summary.
- CLI summary and `--json-out` payload now include reject counts / paths when the profile populates them.

### Changed
- `PhotoPick.summary()` appends a `== rejected ==` block when the profile reports any rejects.

## [0.1.0] — 2026-06-15

### Added
- Initial release: `pick_photos` API, CLI, `default` / `aries` / `big7` profiles, sharpness + exposure composite scoring, optional CLIP classifier via `[clip]` extra.

[Unreleased]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.10.0...HEAD
[0.10.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.9.0...v0.10.0
[0.9.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.8.0...v0.9.0
[0.8.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.7.0...v0.8.0
[0.7.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.5.0...v0.6.0
[0.5.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/MichaelMartinez/PhotoPicker/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/MichaelMartinez/PhotoPicker/releases/tag/v0.1.0
