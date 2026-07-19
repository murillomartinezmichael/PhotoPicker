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

- [ ] **n8n unattended-culling workflow (TODO research item, medium/M).**
  - **What to do:** Decide the intake path (folder on which machine? R2/S3 bucket?), the execution host (n8n cloud cannot run the local `photopicker-cull` CLI — needs a webhook-triggered runner on a machine that has the package installed, or a small Railway service), and the notification channel. Then wire the workflow on michaelmurillo.app.n8n.cloud.
  - **Why blocked on him:** Infrastructure + cost decision (new always-on runner or reuse of an existing box) and account-level n8n changes.
  - **Resumes:** New-shoot arrival auto-culls with `--no-serve --manifest` and notifies with a resume link; first step toward the sellable always-on culling service.

- [ ] **Face/closed-eye detection: model decision (TODO research item, high/M).**
  - **What to do:** Decide whether to (a) bundle the ~230KB YuNet face-detection ONNX from opencv_zoo into the repo (verify its license permits redistribution), and (b) source/train a small open/closed-eye classifier on eye crops — YuNet's 5 landmarks can't compute eye-aspect-ratio, so closed-eye needs its own model + labeled data.
  - **Why blocked on him:** Shipping third-party model weights is a rights/licensing call (LAW 9), and an eye classifier needs training data that doesn't exist in the fleet — an agent inventing/eyeballing one would be fake accuracy.
  - **Resumes:** `photopicker/faces.py` implementation (closed-eyes gate reject + per-profile face weight + face-strip UI) becomes agent-actionable once the model path is settled.
