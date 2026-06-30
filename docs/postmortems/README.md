# Postmortems

After every incident that cost > 30 minutes of investigation OR caused user-visible impact, write a postmortem here.

## Naming
`YYYY-MM-DD-short-slug.md`

## Template
```markdown
# Incident: <short title>

**Date:** YYYY-MM-DD
**Duration:** how long was the impact?
**Severity:** SEV1 | SEV2 | SEV3
**Author:** name

## Summary
One paragraph — what happened, user impact, how it ended.

## Timeline (UTC)
- HH:MM — what was observed / what was done

## Root cause
The actual cause, not a symptom.

## What went well

## What went poorly

## Action items
- [ ] Owner — what — by when
```

## Rule
Blameless. The system, not the individual, failed. The fix is process or code change, not "be more careful."
