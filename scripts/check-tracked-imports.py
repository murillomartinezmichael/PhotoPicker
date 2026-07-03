#!/usr/bin/env python3
"""
check-tracked-imports.py — catch the "forgot to git add" class of prod outage.

Walks a Python project, extracts every top-level `import X` and `from X import Y`
where X points at a first-party package inside the project, and verifies that the
target file is *tracked by git*. Untracked target = the deploy will crash the way
SiteGuide crashed on 2026-07-03 (ModuleNotFoundError on boot from Railway).

Usage:
    # Repo-root invocation (specify project dir)
    python scripts/check-tracked-imports.py SiteGuide
    python scripts/check-tracked-imports.py AI_Manual_Assistant

    # From inside a project (defaults to cwd)
    cd SiteGuide && python ../scripts/check-tracked-imports.py

    # Pre-commit / CI mode — files given as args
    python scripts/check-tracked-imports.py --pre-commit --project SiteGuide Backend/main.py Backend/routers/chat.py

Exit codes:
    0  clean — every local import points at a tracked file
    1  at least one tracked file imports a module whose target is NOT tracked
    2  usage error

Design notes:
    * Only checks first-party packages (top-level dirs that contain __init__.py
      OR any *.py file). Third-party imports (fastapi, anthropic, …) are ignored.
    * Handles `from Backend.rate_limit import RateLimiter` → checks
      Backend/rate_limit.py OR Backend/rate_limit/__init__.py exists AND is
      tracked. If the file exists but is untracked, that's the failure mode
      (exactly the SiteGuide outage).
    * `git ls-files` is the source of truth for "tracked." Files that are
      staged-but-not-committed count as tracked.
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
from pathlib import Path


def git_tracked(project_root: Path) -> set[str]:
    """Return the set of paths tracked by git, relative to project_root, POSIX-style."""
    try:
        r = subprocess.run(
            ["git", "ls-files"],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"error: git ls-files failed: {e}", file=sys.stderr)
        sys.exit(2)
    if r.returncode != 0:
        print(f"error: git ls-files exited {r.returncode}:\n{r.stderr}", file=sys.stderr)
        sys.exit(2)
    return {line.strip() for line in r.stdout.splitlines() if line.strip()}


def first_party_roots(project_root: Path, tracked: set[str]) -> set[str]:
    """Top-level dirs that look like source packages (contain any *.py under them).

    We call these "first-party" — imports rooted here are the ones to check.
    """
    roots: set[str] = set()
    for f in tracked:
        if not f.endswith(".py"):
            continue
        # First path component: "Backend/rate_limit.py" → "Backend"
        parts = f.split("/")
        if len(parts) >= 2:
            roots.add(parts[0])
    # Filter obvious non-packages (tests/, docs/, scripts/ are fine but usually
    # not imported *from* — we keep them; the check is symmetric).
    return roots


def module_to_path_candidates(mod: str) -> list[str]:
    """Given `Backend.rate_limit`, return candidate tracked paths that would satisfy it."""
    parts = mod.split(".")
    return [
        "/".join(parts) + ".py",
        "/".join(parts) + "/__init__.py",
    ]


def find_local_imports(py_path: Path, roots: set[str]) -> list[tuple[int, str]]:
    """Return [(lineno, module_name), …] for imports rooted in first-party packages."""
    try:
        src = py_path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(py_path))
    except (OSError, SyntaxError):
        return []
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # `from X import Y` — module is node.module (None for relative)
            if node.level:  # relative import — skip; git can't validate cheaply
                continue
            mod = node.module or ""
            if not mod:
                continue
            top = mod.split(".", 1)[0]
            if top in roots:
                hits.append((node.lineno, mod))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                if top in roots:
                    hits.append((node.lineno, alias.name))
    return hits


def check_project(project_root: Path, only_files: list[Path] | None = None) -> int:
    tracked = git_tracked(project_root)
    tracked_lower = {t.lower() for t in tracked}  # Windows-friendly compare
    roots = first_party_roots(project_root, tracked)
    if not roots:
        print(f"note: no first-party Python packages found under {project_root}", file=sys.stderr)
        return 0

    # Scope: which files to scan
    if only_files is not None:
        scan = [f for f in only_files if f.suffix == ".py" and f.exists()]
    else:
        scan = [project_root / t for t in tracked if t.endswith(".py")]

    problems: list[tuple[Path, int, str, list[str]]] = []
    for f in scan:
        try:
            rel = f.resolve().relative_to(project_root.resolve()).as_posix()
        except ValueError:
            continue
        # Only enforce on tracked source files — an untracked scratch file
        # importing something untracked isn't a prod-outage risk.
        if rel not in tracked:
            continue
        for lineno, mod in find_local_imports(f, roots):
            candidates = module_to_path_candidates(mod)
            found = any(c.lower() in tracked_lower for c in candidates)
            if not found:
                problems.append((f, lineno, mod, candidates))

    if not problems:
        return 0

    print(f"❌ {len(problems)} tracked file(s) import untracked-or-missing local modules:", file=sys.stderr)
    print("   (this is the crash class SiteGuide hit on 2026-07-03: `ModuleNotFoundError` at boot)", file=sys.stderr)
    print("", file=sys.stderr)
    for f, lineno, mod, cands in problems:
        rel = f.resolve().relative_to(project_root.resolve()).as_posix()
        print(f"  {rel}:{lineno}   imports  {mod}", file=sys.stderr)
        print(f"     expected one of: {', '.join(cands)}", file=sys.stderr)
        # Suggest the fix
        first_cand = cands[0]
        exists_untracked = (project_root / first_cand).exists()
        if exists_untracked:
            print(f"     ▶ FIX: git add {first_cand}", file=sys.stderr)
        else:
            print(f"     ▶ FIX: the file doesn't exist locally either — check for typos or a rename", file=sys.stderr)
        print("", file=sys.stderr)
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify tracked Python files import only tracked local modules.")
    ap.add_argument("project", nargs="?", default=".", help="Project directory (default: cwd)")
    ap.add_argument("--pre-commit", action="store_true", help="Pre-commit mode — only scan files listed after --project")
    ap.add_argument("--project", dest="pc_project", default=None, help="[pre-commit] project root")
    ap.add_argument("files", nargs="*", help="[pre-commit] files to scan (from pre-commit)")
    args = ap.parse_args()

    if args.pre_commit:
        project_root = Path(args.pc_project or args.project).resolve()
        only = [Path(f).resolve() for f in args.files]
        return check_project(project_root, only)

    project_root = Path(args.project).resolve()
    if not project_root.exists():
        print(f"error: {project_root} does not exist", file=sys.stderr)
        return 2
    return check_project(project_root)


if __name__ == "__main__":
    sys.exit(main())
