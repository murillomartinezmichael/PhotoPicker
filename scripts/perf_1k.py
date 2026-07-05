"""Perf harness — verifies the finish-line "1000 photos without dying" claim.

Generates N synthetic photos in a temp folder, times the `cull` pipeline end
to end, and reports total time + per-stage timings + peak RSS memory.

Run:

    .venv/Scripts/python.exe scripts/perf_1k.py           # 1000 photos, top 30
    .venv/Scripts/python.exe scripts/perf_1k.py --n 500 --top 30

Success gate (definition of done):

    500 photos → 30 keepers in under 10 minutes on a typical dev laptop.
    1000 photos → completes without crash or OOM.

Numbers get logged into STATUS.md when this ships a green baseline.
"""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

from photopicker.culler import cull


def _seed_folder(root: Path, n: int) -> None:
    """Write n distinct 900x900 checker-style photos (fast + passes quality gate)."""
    for i in range(n):
        arr = np.full((900, 900, 3), 128, dtype=np.uint8)
        row = (i * 90) % 900
        col = (i * 71) % 900
        arr[row : row + 100, :] = 255
        arr[:, col : col + 60] = 60
        for r in range(0, 900, 16):
            for c in range(0, 900, 16):
                if (r // 16 + c // 16) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = min(255, 200 + (i % 55))
        Image.fromarray(arr).save(root / f"photo_{i:04d}.png")


def _peak_rss_mb() -> float | None:
    try:
        import resource  # POSIX only
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    except ImportError:
        pass
    try:
        import psutil  # optional
        return psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
    except ImportError:
        return None


def _fmt_secs(s: float) -> str:
    if s < 1:
        return f"{s * 1000:.0f}ms"
    if s < 60:
        return f"{s:.2f}s"
    return f"{s / 60:.2f}min"


def run(n: int, top_n: int, keep_folder: bool = False) -> dict:
    tmp = Path(tempfile.mkdtemp(prefix="photopicker_perf_"))
    seed_start = time.perf_counter()
    _seed_folder(tmp, n)
    seed_elapsed = time.perf_counter() - seed_start

    stage_times: dict[str, float] = {}
    current: dict[str, float] = {}

    def _progress(stage: str, done: int, total: int) -> None:
        now = time.perf_counter()
        if stage not in current:
            current[stage] = now
        if done == total:
            stage_times[stage] = now - current[stage]

    paths = sorted(tmp.iterdir())
    print(f"Seeded {len(paths)} synthetic photos in {tmp} ({_fmt_secs(seed_elapsed)})")

    t0 = time.perf_counter()
    result = cull(paths, top_n=top_n, progress=_progress)
    elapsed = time.perf_counter() - t0
    rss = _peak_rss_mb()

    print()
    print(f"=== photopicker cull perf: n={n}, top={top_n} ===")
    print(f"  total elapsed:   {_fmt_secs(elapsed)}")
    for stage, dur in stage_times.items():
        print(f"    {stage:<14} {_fmt_secs(dur)}")
    print(f"  keepers:         {len(result.keepers)}")
    print(f"  rejected:        {result.reject_counts()}")
    if rss is not None:
        print(f"  peak RSS:        {rss:.0f} MB")
    print(f"  input scanned:   {result.input_count}")
    print()

    if not keep_folder:
        shutil.rmtree(tmp, ignore_errors=True)

    return {
        "n": n,
        "top_n": top_n,
        "total_elapsed": elapsed,
        "stage_times": stage_times,
        "keepers": len(result.keepers),
        "rejected": result.reject_counts(),
        "peak_rss_mb": rss,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="PhotoPicker cull perf harness")
    parser.add_argument("--n", type=int, default=1000, help="Number of synthetic photos")
    parser.add_argument("--top", type=int, default=30, help="Top-N keepers to select")
    parser.add_argument(
        "--keep", action="store_true", help="Do not delete the temp folder after run"
    )
    parser.add_argument(
        "--gate-seconds", type=float, default=None,
        help="Exit 1 if total elapsed exceeds this many seconds (CI gate).",
    )
    args = parser.parse_args()

    result = run(args.n, args.top, keep_folder=args.keep)

    if args.gate_seconds is not None and result["total_elapsed"] > args.gate_seconds:
        print(
            f"[FAIL] {_fmt_secs(result['total_elapsed'])} > "
            f"gate {_fmt_secs(args.gate_seconds)}"
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
