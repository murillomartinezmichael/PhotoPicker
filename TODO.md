# PhotoPicker TODO

## SHIPPED this session (2026-07-13, auto-improve tick 6)

- **`--weight` is now scoped to the profile that actually runs.** It used to
  validate against the union of every rule name in the process, so
  `--profile aries --weight clean-lines=1` (a big7 rule) and *any* `--weight` on
  a `--config` profile passed validation and then tuned nothing — the run looked
  retuned and wasn't. Clears the top PARKED item from tick 5's self-review.
- `Profile.rule_names` (registry) + `AestheticRules.names` — a profile now
  declares which rules it ranks with; `cli._check_weights_apply` rejects anything
  else with the rules that *do* exist ("Its rules: ambient-lights, furnished,
  greenery, warmth") or "profile 'backyard' has no tunable rules".
- 5 new tests. **336/336 green, ruff-clean.** Verified for real against
  `demo/shoot` on all three paths (own rule → runs, foreign rule → exit 1,
  config profile → exit 1).

## SHIPPED (2026-07-13, auto-improve tick 5)

- **`--weight NAME=VALUE`** — retunes any profile rule's weight for one run
  (repeatable; `0` disables a rule). Rule names are the ones `--benchmark`
  prints. Unknown name → hard error listing the known rules, never a silent
  no-op. Weights were compile-time constants until now, so "this shoot has no
  golden hour" meant editing `aries.py`.
- `photopicker/profiles/aesthetics.py` — `set_weight_overrides()` /
  `clear_weight_overrides()` / `known_rule_names()`; the rule stack reads the
  override, so ranking *and* the `--benchmark` table move together and the
  0.75x saturation ceiling still holds.
- 14 new tests (`tests/test_weight_overrides.py`). **331/331 green, ruff-clean.**
  Verified for real: `python -m photopicker.cli --folder demo/shoot -p aries
  --dry-run --benchmark --weight warmth=0.9` and the typo path.

## SHIPPED (2026-07-05, v0.14.0 — RUNG 6 UPGRADE)

- `CullProgressBroker` — thread-safe pub/sub with monotonic serial, dedup on identical updates, condition-var wake, idempotent finish (9 unit tests).
- `GET /progress` (JSON snapshot) + `GET /progress/stream` (SSE) endpoints on the web UI. 5-minute wall-clock cap. Handles browser-disconnect cleanly.
- `SessionStore.hydrate(new_session)` — mid-flight swap for the live-progress flow.
- CLI `--live-progress` flag + `_run_live_progress_flow` — browser opens first, cull runs on a background thread that feeds the broker. Vision rerank progress is streamed too. Skipped under `--no-serve` / `--json-out` (those want the sync terminal flow).
- Web UI progress screen (cyan→magenta gradient bar with white cursor tip, monospace stage label with glow, "no photos will be moved" reassurance).
- Bootstrap: `/progress` fetch → SSE subscribe if not finished → hide progress screen + render grid on finish. Backwards-compatible when server boots post-cull.
- Vision-fail hang bug caught in self-review + fixed (missing SDK / rerank exception falls back to offline order + always marks broker finished).
- CHANGELOG v0.14.0, STATUS ladder rung log, pyproject 0.13.0 → 0.14.0.
- **265/265 tests green, ruff-clean.** End-to-end SSE smoke verified (`/progress` snapshot, live stream frames, real broker updates).

## SHIPPED this session (2026-07-05, v0.13.0)

**RUNG 1 HARDEN cycle 2 completed** — v0.12 → v0.13:

- **Vision retry+backoff** (`photopicker/vision.py`) — money code per LAW #7 + DECISIONS D-005. Exponential backoff, jitter, env override, retry event callback wired to CLI progress. 10 tests.
- **Port-in-use auto-fallback** (`photopicker/webui.py::_bind_with_fallback`) — try 10 next ports before failing. 2 tests.
- **--resume malformed-session fallthrough** — returns bool; corrupt / empty / version-drifted files log + fall through to fresh cull instead of `sys.exit`. 3 tests.
- **--output permission errors** → clean `click.echo` + `sys.exit(2)`. Same for `--manifest`. 2 tests.
- **--overwrite / --no-overwrite** — default refuses to write into a non-empty output folder (dotfiles ignored). 3 tests.
- **ImageUnreadable + robust convert** — thumbnail_bytes / vision_bytes raise a named error on decode failure; web UI /photo returns 500 with the filename, Vision rerank skips + logs. 5 tests + 1 integration.
- **`scripts/perf_1k.py`** — 500 photos in **9.44s**, 1000 in **17.74s** on local Windows py 3.10. Well under the 10-min gate. Baseline logged into STATUS.md.
- **`demo/`** — synthetic 40-photo dataset a stranger runs in two commands (`python demo/seed.py && photopicker-cull demo/shoot --top 10`), no API key needed.
- **STATUS.md + DECISIONS.md** scaffolded per Ignition Prompt Phase 0. D-005 documents the retry decision.
- **CHANGELOG v0.13.0 entry, README** rewritten with demo quickstart + perf baseline + new flags table.
- **250/250 tests green, ruff-clean.** Not committed — Michael runs the git add+commit+push.

## NEXT ACTION (60-second cold-open)

**RUNG 7 ENVISION — CHOSEN.** Full proposal at
`docs/PROPOSAL-siteguide-handoff.md` (2026-07-07 · fleet-all-day
checkpoint 6). One-word answer wanted:

- **GO** → I build `photopicker/exports/siteguide.py` + `--export siteguide`
  + `--client SLUG` flag + 5-8 unit tests + docs pass. Two 90-min
  movements, zero new deps. Money path: Aries client-photo turnaround
  collapses from an afternoon → 10 minutes; Big7 job-cadence photo
  blocker becomes "shoot" instead of "shoot + wrangle."
- **PARK** → PhotoPicker moves to Rung VIII RENEWAL and cycles back to
  Rung I HARDEN. The other candidate (CockpitCloud fleet-preview panel)
  stays parked as a nice-to-have.

Rationale for choosing SiteGuide handoff over CockpitCloud preview: the
handoff collapses an actual money path; the preview is a kanban polish
that Mike can add later as a two-hour follow-up once the manifest.json
this proposal already writes exists.

## Rung VII ENVISION candidates (both drafted 2026-07-07)

1. **CockpitCloud fleet-preview panel.** `photopicker-cull` writes each cull's `manifest.json` copy into `~/.cockpitcloud/photopicker/<date>.json`. Cockpit renders a "recent culls" widget showing folder + keeper count + prompt + estimated Vision cost. Ties PhotoPicker into the mission-control loop.
2. **SiteGuide handoff format.** After a client cull, `--export siteguide` bundles keepers + manifest + client-facing README into a zip that drops straight into a Big7 / Aries site's `content/gallery/` Astro content collection — one command from raw shoot to deployable gallery.

Concrete Rung-7 action if the man greenlights either: write `_write_cockpit_ping()` in cli.py (option 1), OR `--export siteguide` mode + `siteguide-gallery.README.md.j2` template (option 2). Both are ≤2-hour work sizes; both directly serve the "connected empire" doctrine.

If neither: return to Rung 1 HARDEN (Ctrl+C during cull thread — graceful broker.mark_finished + server shutdown; unreadable session file after `--resume` — auto-timestamp the corrupt file rather than delete; `--sharpness` calibration table in README).

## PARKED (do not open in this session)

- **Give `config_profile.py` a real rule stack.** Tick 6 made `--weight` on a
  config profile a clean error instead of a silent no-op, but a JSON profile
  still can't declare tunable aesthetic rules at all. Add an optional
  `"rules": [{"name": ..., "label": ..., "weight": ...}]` config key that builds
  an `AestheticRules` and hands its names to `Profile(rule_names=...)`.
- **Flaky test: `test_bind_with_fallback_raises_when_range_exhausted`** — failed
  once in a full run on 2026-07-13, passed on rerun and in isolation. Port-bind
  race against whatever else holds the port; make it bind a real socket it owns
  rather than assuming a range is free.
- **Pillow 14 dedup deprecation** — `Image.Image.getdata` in `photopicker/dedup.py:30` needs migration to `get_flattened_data` before 2027-10-15.
- **Web UI: multi-select drag** — hold Shift + click to select a range, K/X to bulk-decide. Nice but non-critical.
- **Cost telemetry** — track per-run Vision spend (input tokens × price + output tokens × price) and display in the export result box.
- **iCloud shared photostream ingestion** — `photopicker-cull --icloud-album <name>` reads directly from the iCloud sync folder.
- **Cloudflare R2 sink** — `--output r2://bucket/prefix/` uploads keepers to R2 alongside the local copy; useful for the AriesOutdoorLiving-V2 photo CDN work.

## QUESTIONS FOR MIKE

_(none this session — every ambiguity was reversible and logged in DECISIONS.md)_


<!-- AI-HUB-SYNC:START -->
## AI Hub Sync - 2026-07-09

Source of product truth: ..\AI_HUB.md.

**Lane:** photo culling for client sites

**UI/design verdict:** CLI/library is right. If a UI ever appears, it should be a contact-sheet review, not a full photo manager.

**Product improvement:** Document profiles for Big7 and Aries V2, keep tests green, and integrate only at asset intake points.

**Next action:**
- [ ] Document best profile/use command for Big7 and Aries V2.

**Combine/separate call:** Shared utility; prevent duplicate photo pickers.

**Verification gate:** pytest; profile fixture tests; CI.
<!-- AI-HUB-SYNC:END -->
