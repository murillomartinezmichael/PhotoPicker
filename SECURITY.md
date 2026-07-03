# Security Policy

## Reporting a vulnerability

If you believe you've found a security vulnerability in PhotoPicker, please **do not file a public GitHub issue**. Public disclosure puts users at risk before a fix is available.

Instead, report privately via:

- **Email:** murillomartinezmichael@gmail.com
- **Subject:** `[security] PhotoPicker — short description`

Include:
- A description of the issue
- Steps to reproduce
- Affected versions / commits
- Your assessment of the impact
- Any proof-of-concept code (kept confidential)

## What to expect

- **Acknowledgment** within 72 hours
- **Initial assessment** within 7 days
- **Fix + disclosure plan** communicated within 30 days for confirmed issues

We'll credit you in the release notes unless you prefer to remain anonymous.

## Scope

In scope:
- The application source code in this repository
- Deployed instances we operate (production URLs documented in `RUNBOOK.md`)

Out of scope:
- Social engineering against the maintainer
- Denial-of-service against rate-limited endpoints
- Vulnerabilities in third-party dependencies (report those upstream)
- Issues requiring physical access to a user's machine

## Supported versions

Latest `main` and the most recent tagged release. Older versions are not patched unless they're still in production deployments we operate.


## Secret rotation

Per [`docs/SECURITY_STANDARDS.md`](../docs/SECURITY_STANDARDS.md), every secret this project uses is rotated on a schedule. Update the table below at rotation time.

| Secret | Cadence | Owner | Last rotated |
|---|---|---|---|
| _e.g. `ANTHROPIC_API_KEY`_ | 90 days | Michael | YYYY-MM-DD |
| _e.g. `OAUTH_REFRESH_TOKEN`_ | Annually or on suspected compromise | Michael | YYYY-MM-DD |
| _e.g. `ADMIN_KEY` (per deploy)_ | 90 days | Michael | YYYY-MM-DD |

Removed a secret? Delete its row. Added one? Add its row *before* the next
deploy — the audit expects this table to reflect the live secret set.

Rotation runbook: see `RUNBOOK.md` § "Rotate a secret" (or `SECURITY_AUDIT.md`
§5 at the repo root for a worked example across projects).
