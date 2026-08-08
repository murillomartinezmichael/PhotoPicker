"""Override-rate aggregator — the honest accuracy number, measured not claimed.

Competitors publish self-benchmarked accuracy claims; the metric that actually
means something is override rate: the % of pipeline picks a human reverses
during review. Every web-UI session already persists K/X decisions to
`.photopicker-session.json`, so this script walks one or more shoot folders,
computes per-session override stats, and prints the aggregate.

Run:

    python scripts/override_rate.py ~/photos/aries_shoot ~/photos/big7_shoot
    python scripts/override_rate.py --root ~/photos     # recurse for sessions

Once a few real Aries/Big7 shoots have been reviewed, the aggregate line here
is the number the README accuracy claim cites (never a made-up one).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Session files are plain JSON — read them directly so this script works on a
# checkout without an installed package. Field semantics mirror
# `photopicker.webui._override_stats`: picks = candidates without a
# rejected_reason; override = a pick the human rejected; undecided = kept.
SESSION_FILE = ".photopicker-session.json"


def session_stats(session_path: Path) -> dict | None:
    """Compute override stats for one session file. None when unusable/empty."""
    try:
        data = json.loads(session_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    candidates = data.get("candidates", [])
    picks = [c for c in candidates if not c.get("rejected_reason")]
    if not picks:
        return None
    overridden = sum(1 for c in picks if c.get("decision") == "reject")
    decided = sum(1 for c in picks if c.get("decision"))
    rescued = sum(
        1
        for c in candidates
        if c.get("rejected_reason") and c.get("decision") == "keep"
    )
    return {
        "folder": str(session_path.parent),
        "picks": len(picks),
        "decided": decided,
        "overridden": overridden,
        "rescued": rescued,
    }


def find_sessions(folders: list[Path], root: Path | None) -> list[Path]:
    found: list[Path] = []
    for folder in folders:
        candidate = folder / SESSION_FILE
        if candidate.exists():
            found.append(candidate)
    if root is not None:
        found.extend(p for p in sorted(root.rglob(SESSION_FILE)) if p not in found)
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "folders",
        nargs="*",
        type=Path,
        help="Shoot folders that contain a .photopicker-session.json",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Also recurse this directory for session files.",
    )
    args = parser.parse_args()
    if not args.folders and args.root is None:
        parser.error("give at least one folder, or --root to recurse")

    sessions = find_sessions(args.folders, args.root)
    stats = [s for s in (session_stats(p) for p in sessions) if s is not None]
    if not stats:
        print("No usable session files found — review a shoot in the web UI first.")
        return 1

    total_picks = total_overridden = total_rescued = 0
    undecided_sessions = 0
    for s in stats:
        rate = s["overridden"] / s["picks"]
        note = "" if s["decided"] else "  (no decisions yet)"
        print(
            f"{s['folder']}: kept {s['picks'] - s['overridden']}/{s['picks']} picks "
            f"— {round(rate * 100)}% override"
            + (f" · rescued {s['rescued']}" if s["rescued"] else "")
            + note
        )
        if s["decided"]:
            total_picks += s["picks"]
            total_overridden += s["overridden"]
            total_rescued += s["rescued"]
        else:
            undecided_sessions += 1

    if total_picks:
        rate = total_overridden / total_picks
        print(
            f"\nAggregate over {len(stats) - undecided_sessions} reviewed "
            f"session(s): kept {total_picks - total_overridden}/{total_picks} "
            f"picks — {round(rate * 100)}% override"
            + (f" · rescued {total_rescued}" if total_rescued else "")
        )
    else:
        print("\nNo session has human decisions yet — aggregate skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
