# Contributing to PhotoPicker

Thanks for considering a contribution.

## Before you start

- Read `README.md` (what + setup) and `ONBOARDING.md` (day-by-day if you're new)
- Read [`../docs/ENGINEERING_STANDARDS.md`](../docs/ENGINEERING_STANDARDS.md) — repo-wide rules
- For non-trivial changes, open an issue first and propose the approach

## Local setup

```bash
./build.sh        # Unix / macOS
build.bat         # Windows
```

If `build.sh` fails on a fresh clone, file an issue — that's a build-script bug, not your environment.

## Workflow

1. Branch from `main`:
   - features: `feat/short-name`
   - fixes: `fix/short-name`
   - chores: `chore/short-name`
2. Make your change. Follow `ENGINEERING_STANDARDS.md` § 2 (naming + comments).
3. Add tests at the right tier (see `../docs/TESTING_STANDARDS.md`).
4. Lint + test locally. The make targets call `.venv` directly, so install the
   dev tools into it once (`.venv/Scripts/pip` on Windows): `pip install -e ".[dev]"`.
   ```bash
   make lint   # ruff check photopicker tests — same invocation as CI
   make test   # full pytest suite + coverage (one suite; no unit/integration/e2e tiers)
   ```
5. Open a PR using the template. Be specific in "How tested."
6. Address review comments by pushing more commits — don't force-push during review.
7. Squash on merge (default).

## Commit messages

```
<type>: <imperative summary>

<optional body explaining WHY>
```

Types: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`.

Example: `feat: add page citations to RAG answer response`.

## Code style

- Run the language's blessed formatter (`ruff format`, `dotnet format`, `prettier`, `gofmt`) before pushing
- CI fails on lint warnings — no exceptions

## Reporting bugs

Use the **Bug report** issue template. Include version / git SHA, environment, steps, expected vs actual, sanitized logs.

## Reporting a security issue

Do NOT file a public issue. See `SECURITY.md`.

## License

By contributing you agree your contribution is licensed under the project's `LICENSE` file.
