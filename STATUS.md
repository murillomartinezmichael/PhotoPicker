# PhotoPicker STATUS

**As of 2026-10-03: local preparation EXHAUSTED_HERE; not release-ready or published.**

PhotoPicker is the existing library/CLI and local contact-sheet review utility for
client-site asset intake. Big7 and Aries V2 profile/export commands are documented
in RUNBOOK.md. Keep this utility; no replacement photo manager, cloud API or fleet
integration was added.

Candidate: `session/2026-08-07-ci-repair`, changes based on `7710fb15dd081d049fe5b53edecb8267a06065bd`.
The exact reviewed commit is in the fleet's `photopicker/ui-qualification/LOCAL_COMMIT.json`.
Package metadata remains 0.14.0; main remains `c628198bafda41d546c76309c4e47ea8f0148e97`.
No push, main integration, model/provider call, private-photo use or publication.

## Current local evidence

- 429 offline pytest cases passed on Windows/Python3.10.11; Python statement
  coverage 89.11% (1915/2149). Actual `tests/test_faces.py` inference excluded
  before collection; faces.py remains in the coverage denominator. Other model
  tests use stubs/fake clients. No semantic-quality claim.
- Pinned Ruff0.15.20 passes. Declared Linux/Python3.10/3.11/3.12 CI is not run here.
- Existing metadata/HEIC/JPEG/WebP/thumbnail exports, profile fixtures, HTTP request
  guards, literal filenames, burst selection and restart evidence retained.
- Actual Chrome154 local-handler review: keyboard, dialog focus/return, Escape,
  reduced motion and 1280/390/320px layouts pass; 12 broad axe4.13 scans had no
  violations. Follow-up corrected two ARIA groups and photo-overlay contrast;
  targeted checks pass. Scanner manual-review contrast flags are documented,
  not a claim of full accessibility certification.
- Seven actual Windows launcher success/help/error checks pass, including a path
  with spaces and an ampersand. Originals remain unchanged.

Usable code and evidence: [candidate return](docs/verification/ui-2026-10-03/TASK_RETURN.md),
[machine-readable requirements](docs/verification/ui-2026-10-03/REQUIREMENTS.json),
[joint plan](docs/verification/ui-2026-10-03/JOINT_ACCEPTANCE.json).

## Remaining release work

- **PP-TARGET-MATRIX:** approved package environment with the declared `wheel`
  dependency, fresh candidate wheel/sdist + hashes, artifact install/CLI smoke
  and declared Python matrix. Current build1.5.0/setuptools78.1.0 exist; wheel
  is missing. No dependency installation was authorized or performed.
- **PP-JOINT-ACCEPTANCE:** Michael and agent record independent observations in
  the joint plan. Narrator, high contrast, physical DPI and actual client-shoot
  quality/performance remain unverified; real media and optional models require
  their approved custody/execution route. Publish no fabricated accuracy claim.
- **PP-RELEASE-DECISION:** Michael reviews the exact candidate and package/matrix/
  joint evidence, then decides main integration and separately authorizes any
  push/account/upload. Historical dist files are not current candidate artifacts.

## Held proposals and historical evidence

SiteGuide handoff format, CockpitCloud cull panel, RAW expansion, private-cloud
intake/R2 and other parked proposals were not reactivated. The historical n8n
workflow remains inactive; its cancelled plan is not renewed by this campaign.
Live cull progress already exists via SSE; old "post-cull only" notes were stale.
Historical performance on 2026-07-05 was 9.44s/500 and 17.74s/1000 synthetic photos
on local Windows/Python3.10. This is not current-candidate performance or provider
latency/billing evidence. Optional provider pricing and billing route are unverified.

The following dated implementation log is historical, not current release proof.

## Ladder progress log

| Date | Rung | Note |
|---|---|---|
| 2026-07-05 | Cycle 1 complete | v0.11 shipped cull vertical (culler + webui + vision + CLI + 61 tests). |
| 2026-07-05 | Cycle 1 complete | v0.12 shipped sharpest-per-cluster + filter chips + resume + manifest + EXIF preservation tests (222/222 green). |
| 2026-07-05 | **RUNG 1 HARDEN** done | v0.13: Vision retry+backoff, port fallback, malformed-session fallthrough, output/manifest permission errors, --overwrite guard, ImageUnreadable + web-UI 500 with filename, perf harness (500→9.4s / 1000→17.7s), demo folder, 250/250 tests, ruff-clean. |
| 2026-07-05 | **RUNG 6 UPGRADE** done | v0.14: `CullProgressBroker` + `/progress` JSON + `/progress/stream` SSE + `SessionStore.hydrate` + `--live-progress` CLI + browser-first flow + progress-screen frontend. Vision-fail hang bug caught in self-review + fixed (falls back to offline order). 265/265 tests green (15 new: 9 broker + 3 HTTP + 3 CLI), ruff-clean. |
| 2026-07-06 | Rung 6 continued | Big7 profile: clean-lines aesthetic bonus (weight 0.3) stacked additively on top of the people bonus. Rewards straight-framing / level-horizon shots that read as construction craftsmanship. 3 new tests: math, ranking-within-bucket, ordering-invariant (people-only still beats clean-lines-only). **273/273 tests green (was 270), ruff-clean.** `photopicker/profiles/big7.py` at 100% coverage. |
