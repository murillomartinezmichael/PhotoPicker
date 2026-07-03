<!--
  PR template — drop into .github/PULL_REQUEST_TEMPLATE.md at repo root.
  GitHub will use this as the default PR body.
-->

## What

<!-- One or two sentences. What changes in this PR? -->

## Why

<!-- The problem this solves or the reason for the change. Link tickets. -->

Closes #

## How tested

<!-- Concrete steps. "Ran the suite" is not enough — what scenarios? -->

- [ ] Unit tests added / updated
- [ ] Integration tests added / updated (if external boundary changed)
- [ ] E2E tested manually or via Playwright (if user-facing)
- [ ] Lint passes locally

## Screenshots / output (if UI or output change)

<!-- Before / after, or sample output. -->

## Risk + rollback

<!-- What's the worst that could happen on merge? How would we roll back? -->

## Checklist

- [ ] Names follow `../docs/ENGINEERING_STANDARDS.md` § 2
- [ ] CRUD layering intact (no SQL in routes, no HTTP imports in services)
- [ ] No secrets in the diff (`gitleaks` will catch but check anyway)
- [ ] No commented-out code
- [ ] Docs updated (`README`, `RUNBOOK`, `CHANGELOG` as applicable)
- [ ] No new dependency without a reason in the PR description
