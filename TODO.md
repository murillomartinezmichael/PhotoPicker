# PhotoPicker TODO

## SHIPPED this session (2026-07-20, fleet re-audit)

- **Finished the burst-similarity/keeper-swap feature left dirty+broken by
  the 2026-07-19 interrupted session** (see `WIP_HANDOFF_2026-07-19.md`,
  now resolved and removed). That work-in-progress had leaked cluster-loser
  paths into `CullResult.scores`, breaking the keepers-only public contract
  (`test_cull_returns_top_n_from_folder` was red: 374 passed, 1 failed).
  Restored the contract and added a new `CullResult.all_scores` field
  (every scored survivor, not just keepers) so cluster-loser scores are
  still reachable for the web UI's burst-compare/swap feature without
  changing what counts as a "keeper."
- 16 new tests covering `dedup_perceptual_clusters`, the culler
  clusters/all_scores contract, `build_session`'s `similar` list, and
  `SessionStore.swap` (unit + HTTP `/swap` + `/photo?m=`).
  **391/391 tests green, ruff-clean.**
- **Face/closed-eye detection shipped** (Mike's model decision, same day):
  `photopicker/faces.py::face_eye_score()` using MediaPipe Face Mesh —
  Apache License 2.0, pinned `mediapipe==0.10.21` (later versions dropped the
  offline legacy API this uses). Published Eye Aspect Ratio (EAR) technique
  against iris-refined landmarks, no training/labeled data needed. Wired
  into `culler.cull(..., face_gate=True)` / CLI `--faces` (default off —
  0.4x score penalty when the worst detected face's eyes are closed, no
  penalty when no face is found). New `[faces]` extra in `pyproject.toml`.
  7 new tests in `tests/test_faces.py` (importorskip-guarded, matching the
  CLIP/vision pattern), including a real culler-ranking integration test
  proving the gate flips which frame of a synthetic "burst" pair survives
  dedup. Verified against real synthetic face images (open EAR ~0.41-0.46,
  closed EAR ~0.11-0.17 — both sides of the published 0.2 threshold).
  **398/398 tests green, ruff-clean.** Resolves the PENDING_MANUAL model
  decision and the competitor-research item below (cv2/YuNet + trained
  classifier plan superseded by the pretrained-landmark approach).

## SHIPPED this session (2026-07-14, auto-improve tick 8)

- **A corrupt photo is now rejected as `unreadable`, not `duplicates`.**
  `dedup_perceptual` caught the hash failure and *dropped* the path. Dedup runs
  before the quality gate in `aries-gallery` and every config profile, so a
  truncated/corrupt file never reached the gate that knows how to name it — it
  landed in the caller's `duplicates` reject bucket under a reason that was
  simply false, and a client asking "why was this cut?" got a wrong answer.
  Unhashable photos now pass through to the gate.
- **Pillow 14 deprecation cleared** (top PARKED item): `average_hash` reads
  `Image.tobytes()` instead of the removed `Image.getdata()`. Same per-pixel
  bytes for an `"L"` image, so hashes are unchanged.
- 3 new tests (dedup pass-through ×2, config-profile end-to-end reject reason).
  **357/357 green, ruff-clean.**

## SHIPPED (2026-07-13, auto-improve tick 7)

- **A `--config` JSON profile can now declare its own aesthetic rules.** New
  optional `"rules": [{"name", "label", "weight"}]` key (plus `"max_bonus"`)
  builds a real `AestheticRules` stack, so a config profile ranks on
  quality × CLIP bonuses like `aries`/`big7` instead of bare quality — and its
  rule names flow into `Profile.rule_names`, which means `--benchmark` prints
  its contributions and `--weight NAME=VALUE` retunes them. Onboarding a new
  site now needs zero Python. Clears the top PARKED item from tick 6.
- Malformed rules fail loudly at build time (missing name/label, non-numeric or
  negative weight, duplicate name, bad `max_bonus`) — never a silent no-op.
  `--weight` on a config profile with *no* `rules` key still errors, now with a
  message that points at the key.
- 18 new tests (`tests/test_config_rules.py`), `config_profile.py` at 100%
  coverage. **354/354 green, ruff-clean.** Verified end-to-end against
  `demo/shoot`: benchmark table prints warmth/greenery contributions and the
  `--weight warmth=0.9` override moves the numbers.
- **Flaky port test fixed** (2nd PARKED item cleared). Both
  `_bind_with_fallback` tests bound one port and *assumed* the next few were
  free — anything else on the box holding `base+2` failed the setup, not the
  code. New `_reserve_ports(n)` helper binds a contiguous run the test actually
  owns and retries elsewhere if the run is broken up. Also caught a real bug in
  the old test: `tries=3` walks *four* ports (`range(tries + 1)`), so
  "exhausted" now holds four. 6/6 clean reruns.

## SHIPPED (2026-07-13, auto-improve tick 6)

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

- **Reject reasons aren't surfaced in the CLI.** The `Selection.rejected` map is
  populated (and now honest — see tick 8) but only the manifest carries it. A
  `--why-rejected` flag printing `name → reason` would close the loop for the
  "why was my best shot cut?" question. ~40 lines + tests.
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

---

## Competitor research — vetted upgrades (2026-07-19)

38-agent adversarial research pass (independent researcher + critic per product, claims spot-verified against live competitor sites). Full fleet report: `../docs/research/COMPETITOR_RESEARCH_2026-07-19.md`.

**Top competitors studied:** Aftershoot (Selects), Narrative Select, FilterPixel, Optyx, Imagen Culling Studio

### Upgrades (impact-ranked)

- [ ] **[high/S] (design-patterns)** Render the existing ai_reason string plus a small stat block in the Enter/focus view: composite score, sharpness percentile computed client-side from the session's score list, and reject reason for culled frames. All data is already in the Session JSON — this is HTML/JS in the one webui.py file, zero backend, zero new data.
  - *Pattern source:* FilterPixel's verified headline differentiator is a score plus plain-English reason on every selection; the verified Tov Studio 2026 teardown dings Aftershoot for showing none. PhotoPicker's focus view renders only 'quality NN · ai NN' (webui.py ~1141/1420) even though its session/manifest already carries score, ai_score, and an ai_reason text field the UI never displays.
- [ ] **[high/S] (flow)** Add --xmp to photopicker-cull. Corrected spec: Lightroom ignores .xmp sidecars for JPEG/HEIC (sidecars are RAW-only), and JPEG/HEIC is all PhotoPicker reads — so embed the XMP APP1 packet (xmp:Rating scaled by rank) directly into exported JPEG copies via a stdlib byte-level segment splice (export already writes copies, so originals stay untouched). Skip HEIC embedding; add sidecars only when RAW support lands.
  - *Pattern source:* Optyx's whole integration story (verified) is writing star ratings and color labels to XMP that Lightroom picks up, so it slots into existing pro workflows. PhotoPicker's cull results are invisible to every pro tool — export only copies files.
- [x] **[high/S] (positioning)** PACKAGING PREPPED 2026-07-20 — Mike decided to publish; pyproject.toml metadata completed (classifiers, project.urls, license, author email), `python -m build` produces a verified wheel+sdist, `twine check` passes, fresh-venv smoke-import confirmed. See `PUBLISHING.md` for the exact `twine upload` steps and `PENDING_MANUAL.md` for the remaining account/token gate (Mike-only). README repositioning ('photo culling for pipelines' rewrite) is NOT done — that's a separate content/positioning task, out of scope for this packaging pass.
  - *Pattern source:* All five competitors are GUI apps fighting for the same wedding photographer; none sells a scriptable library, yet FilterPixel's own guide calls overnight-pipeline integration the biggest ROI. PhotoPicker already is the pipeline product (pip-installable, pick_photos() API, --json-out/--no-serve, deterministic, README-claimed 222 green tests; repo actually has ~340 test functions) but its README positions it as a personal tool.
- [x] **[high/M] (features)** SHIPPED 2026-07-20 as `photopicker/faces.py` — superseded spec: Mike picked MediaPipe Face Mesh (Apache 2.0 pretrained landmark model) over the YuNet-plus-trained-classifier plan below, since MediaPipe's iris-refined landmarks support the Eye Aspect Ratio technique directly (no training data needed). Wired into `cull(..., face_gate=True)` / CLI `--faces` (opt-in, not a hard quality-gate reject — a 0.4x score penalty). Face-crop strip / eye badges in the focus view UI is still open as a follow-up, not done today.
  - *Original pattern source:* All five competitors detect faces and closed eyes (Aftershoot flags, Narrative Eye Assessments, Optyx expression/blink scores — all verified). PhotoPicker's offline scoring is Laplacian sharpness + mean-luminance exposure only (scoring.py); no face code exists anywhere in the package, so a sharp shot of a client mid-blink wins the cull unless the optional paid Vision rerank runs.
- [ ] **[high/M] (features)** Corrected spec: this is NOT just surfacing existing data — dedup_perceptual must return a cluster map, threaded through CullResult and Session (new plumbing, hence M). Then render a '+N similar' chip on clustered keepers that expands to a side-by-side compare row with one-key swap-pick.
  - *Pattern source:* Aftershoot Survey Mode, Narrative Scenes View, and Optyx Autogroup (all verified) let users see a burst side-by-side and swap the pick. PhotoPicker's dedup_perceptual keeps the highest-scored frame per cluster and dumps the rest into a flat near-duplicate reject list — cluster membership is thrown away, so the user can never swap in the better expression.
- [ ] **[medium/S] (trust)** The web UI already persists every K/X decision against pipeline picks in .photopicker-session.json (verified in webui.py). Print an override-rate line at export ('kept 27/30 picks — 10% override') plus a small cross-session aggregation script; publish the measured number in the README after a few real Aries/Big7 shoots.
  - *Pattern source:* Competitors lead with accuracy claims (FilterPixel's self-benchmarked 94%, Narrative's 1B+ images/yr); the verified Tov Studio teardown says the honest metric is override rate — the % of AI picks a human reverses after real shoots, with good tools landing 5–15%. PhotoPicker publishes speed and nothing on accuracy.
- [ ] **[medium/M] (flow)** Wire one n8n workflow on the already-running michaelmurillo.app.n8n.cloud instance: watch an intake folder/bucket per client site, run photopicker-cull --no-serve --manifest on new-shoot arrival, notify with the manifest and a web-UI resume link. Internal fleet leverage first; a sellable always-on culling service later.
  - *Pattern source:* FilterPixel's guide and the Tov teardown both name unattended overnight culling as the biggest ROI, and no incumbent sells it as a service. PhotoPicker requires a manual CLI invocation per shoot.
- [ ] **[medium/M] (features)** Add a [raw] extra using rawpy: extract_thumb() pulls the embedded JPEG preview without demosaicing, keeping the per-photo latency budget; hook the existing _load_grayscale/convert seam. Demoted rationale: current fleet shoots are phone HEIC/JPG, already covered — this only matters for the photographer/automation wedge, so ship it after the PyPI positioning gap, not before.
  - *Pattern source:* Aftershoot, Narrative, FilterPixel, and Optyx are all RAW-first (CR2/NEF/ARW/DNG). PhotoPicker reads only what Pillow+pillow-heif opens (JPG/HEIC/PNG) — verified: no rawpy or RAW extension anywhere in the repo — so any real camera body produces a folder it cannot cull.

### Quick wins (<1 day each)

- [ ] Reason panel in the focus view (half day): the session JSON already carries per-photo score, ai_score, and an ai_reason string the UI never renders — display them plus a client-side sharpness percentile in the Enter view. Matches FilterPixel's verified headline differentiator and the confirmed no-reasoning criticism of Aftershoot.
- [ ] Override-rate line at export (2–3 hours): compare the K/X decisions already persisted in .photopicker-session.json against pipeline picks and print 'kept 27/30 — 10% override'. The honest accuracy metric per the verified Tov Studio teardown, and the seed for a defensible README accuracy claim.
- [ ] XMP ratings export (1 day): embed xmp:Rating into exported JPEG copies via a stdlib APP1 segment splice — corrected from the original sidecar spec, since Lightroom ignores .xmp sidecars for JPEG/HEIC. Copies Optyx's verified Lightroom-integration pattern with no new dependencies.
