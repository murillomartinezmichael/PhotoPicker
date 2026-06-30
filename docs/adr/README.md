# Architecture Decision Records (ADRs)

ADRs capture **why** we made a non-obvious architectural choice. They live forever — the code may change, but the rationale stays.

## When to write one

Write an ADR when:
- You picked one option over another and the loser had merit (i.e., it's not "everyone obviously uses X")
- The decision constrains future work (DB engine, language, framework, key library, deploy platform)
- You'd otherwise be asked "why did we do this?" in 6 months and not remember
- You introduced something unusual a future contributor would question

**Don't** write one for trivial choices ("we picked tab over spaces").

## How

1. Copy `template.md` to `docs/adr/NNNN-short-title.md` (NNNN is next sequential number)
2. Fill it in
3. PR it like any other code change
4. Mark previous ADRs as `Superseded by ADR-NNNN` when later decisions override them; never delete

## Status values

- **Proposed** — under discussion
- **Accepted** — current
- **Deprecated** — no longer the recommended approach, but nothing has replaced it
- **Superseded by ADR-NNNN** — a later ADR replaces this one

## Tone

ADRs are short — 1-2 pages. They are not architecture documents. They explain ONE decision.
