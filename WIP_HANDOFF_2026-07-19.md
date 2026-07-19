# Interrupted-work handoff — 2026-07-19

## Burst similarity / keeper swap

Status: incomplete and currently regression-producing.

- Dirty changes span CLI, culler, dedup, and Web UI without feature-specific tests.
- Ruff passes.
- The full suite fails `tests/test_culler.py::test_cull_returns_top_n_from_folder`: `CullResult.scores` now contains non-keeper entries (374 passed, 1 failed).

Next: restore the public result contract, or deliberately revise it with migration coverage; add cluster/swap tests; rerun all 375 tests before committing the code.
