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
