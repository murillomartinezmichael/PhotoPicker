# PENDING_MANUAL — PhotoPicker

Manual gates only Mike can clear. Each item: What / Why / Resumes + a checkbox.
Agent keeps working past these; sweep on your own cadence.

- [ ] **Publish photopicker 0.14.0 to PyPI.**
  - **What to do:** Create/log into a PyPI account, mint an API token, then from the repo root: `python -m pip install build twine && python -m build && python -m twine upload dist/*`.
  - **Why blocked on him:** Account creation + credential handling — agents don't own accounts or tokens.
  - **Resumes:** README "Install" section flips to `pip install photopicker`; the dev/automation-wedge positioning (TODO research item, 2026-07-19) is fully live. Package metadata (readme/license/classifiers) is already prepped and wheel-build verified.

- [ ] **Publish a measured override-rate number in the README.**
  - **What to do:** After reviewing 3+ real Aries/Big7 shoots in the web UI, run `python scripts/override_rate.py --root <photos root>` and paste the aggregate line into README (Status or a small "Accuracy" note).
  - **Why blocked on him:** The number must come from real human review sessions — fabricating or extrapolating it is banned (LAW 6). Only Mike culls real client shoots.
  - **Resumes:** README gets a defensible accuracy claim competitors can't match (they publish self-benchmarks; this is measured override rate).

- [ ] **n8n unattended-culling workflow — skeleton shipped 2026-07-20, needs credential + architecture decision to go live.**
  - **What's built:** `PhotoPicker — Drive Watch & Notify (INCOMPLETE, deactivated)` at `michaelmurillo.app.n8n.cloud` (workflow id `1gocNDVxuR5yatlB`, https://michaelmurillo.app.n8n.cloud/workflow/1gocNDVxuR5yatlB). Google Drive Trigger (fileCreated, polls every 15 min) → Normalize File Info → Gmail notify to murillomartinezmichael@gmail.com. **Left deactivated.** Validated with `validate_workflow` and test-executed (`test_workflow`, execution 1426, success) using simulated pin data.
  - **Confirmed architecture limit:** this n8n instance is Cloud-hosted. `n8n-nodes-base.executeCommand` is not even a recognized node type on it (validator rejected it outright), and SSH is very likely the same — n8n Cloud does not expose shell/SSH execution nodes. **"n8n shells out to the local `photopicker-cull` CLI" cannot work on this instance, full stop** — not a config problem, an unavailable-node problem.
  - **What to do:** (1) Add/select a Google Drive credential on this n8n instance (none exists — checked via `list_credentials`), then set the trigger's `folderToWatch` to the real folder. (2) Decide the execution path for the actual cull, since Execute Command/SSH are off the table — options logged on the workflow's sticky note: (a) PhotoPicker exposes a small HTTP endpoint n8n can POST to (new PhotoPicker code, not built), (b) a local runner/agent on a machine with PhotoPicker installed polls or receives a webhook and shells out itself, (c) skip Drive and run `photopicker-cull` on a schedule against already-synced storage (e.g. Railway cron).
  - **Why blocked on him:** Google Drive credential + folder choice is an account-level n8n change; the execution-path pick is an infra/cost decision plus (if option a) new PhotoPicker scope that needs to be greenlit separately.
  - **Resumes:** Once credential + path are chosen, the workflow gets its missing execution node wired in and can be activated; culling stays notify-only until then.

- [x] **Face/closed-eye detection: model decision — RESOLVED 2026-07-20, shipped same day.**
  - **Decision:** Mike picked a permissively-licensed pretrained model over training one — MediaPipe Face Mesh (Apache License 2.0, Google), using the published Eye Aspect Ratio (EAR) technique against its iris-refined landmarks. No training/labeled data needed, unlike the YuNet + custom-classifier path this item originally scoped.
  - **Shipped:** `photopicker/faces.py` (`face_eye_score()`), wired into `culler.cull()` behind `face_gate=False` default / `--faces` CLI flag (opt-in — never changes existing profile behavior silently). New `[faces]` extra in `pyproject.toml` (`pip install "photopicker[faces]"`), pinned `mediapipe==0.10.21` (0.10.22+ dropped the offline legacy API this module uses). Tests in `tests/test_faces.py` (7 new, all green) — includes a real culler-ranking integration test proving the eye-open frame gets kept over an otherwise-sharper closed-eye frame once the gate is on.
  - **Not done:** Not installed in CI (matches how `[clip]`/`[vision]` are handled — opt-in extras aren't part of the default matrix). Not wired into any built-in profile (aries/big7/default/aries-gallery) — CLI-level `cull()` only, per today's scope. A future ask to gate a themed profile on face/eye state is a small follow-up, not blocked on anything.
