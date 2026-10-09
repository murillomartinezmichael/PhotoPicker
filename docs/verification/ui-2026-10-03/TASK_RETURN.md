# PhotoPicker local completion — 2026-10-03

**EXHAUSTED_HERE for the approved local scope; not release-ready or published.**

Codex /root completed useful current-environment work on the existing candidate.
Michael retains package, real-media/model, main-integration and publication decisions.

The usable candidate now preserves export metadata, validates local UI requests,
renders filenames literally, restores burst choices safely, supports keyboard/
compact review and correctly forwards Windows command arguments and exit codes.
No new photo manager, cloud API or parked integration was introduced.

## Evidence

- 429 offline tests, 89.11% Python coverage (1915/2149), Ruff0.15.20 pass.
  Actual face inference was excluded before collection; models/providers remain unverified.
- 37 keyboard/layout checks across 1280/390/320px and 12 broad axe scans passed.
  Follow-up checked ARIA groups and contrast; 16 final caption/help-layout checks
  and 13 burst/export regression checks passed. See QUALIFICATION.json for reuse
  boundaries and scanner manual-review limits.
- Seven actual Windows cmd.exe success/help/error checks passed with synthetic
  photo paths containing spaces and an ampersand. Originals are unchanged.
- Earlier metadata and burst returns retain the actual exported images/manifests.
  Four current UI screenshots and machine-readable checks are in this directory.

## Use and remaining work

From the PhotoPicker checkout, `run.bat cull "<approved synthetic folder>"
--top 1 --no-ai --no-serve --json-out` exercises the installed local route.
`run.bat pick "<approved synthetic folder>" --profile default --dry-run --json-out`
previews without invoking CLIP or writing exports. `run.bat cull --help` and
`run.bat pick --help` show their own options.

PP-TARGET-MATRIX needs an approved build environment with the declared wheel
dependency, fresh candidate artifacts and declared Python matrix results.
PP-JOINT-ACCEPTANCE needs Michael's independent observations in the editable
JOINT_ACCEPTANCE.json; private photos and optional models keep their own gates.
PP-RELEASE-DECISION needs the exact reviewed candidate/package/joint evidence and
Michael's integration decision; pushes and uploads remain separately gated.
REQUIREMENTS.json contains each gate's owner, prerequisite and acceptance check.

Base revision: `7710fb15dd081d049fe5b53edecb8267a06065bd`; SOURCE_HASHES.json binds
the final code. Exact post-review commit receipt is under the root fleet proof's
`photopicker/ui-qualification/LOCAL_COMMIT.json`. Main remains unchanged.
Root continues independent fleet work; this is not the final fleet handoff.
