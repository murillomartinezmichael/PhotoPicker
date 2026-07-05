"""Generate synthetic photos into `demo/shoot/` for the readme walkthrough.

Two-clicks-from-nothing: this file exists so someone who just cloned the repo
can `python demo/seed.py && photopicker-cull demo/shoot --top 10` and see it work
without touching a real camera roll.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image

N_PHOTOS = 40
SIZE = 900


def main() -> None:
    root = Path(__file__).parent
    shoot = root / "shoot"
    if shoot.exists():
        shutil.rmtree(shoot)
    shoot.mkdir(parents=True)

    for i in range(N_PHOTOS):
        arr = np.full((SIZE, SIZE, 3), 128, dtype=np.uint8)
        row = (i * 90) % SIZE
        col = (i * 71) % SIZE
        arr[row : row + 100, :] = 255
        arr[:, col : col + 60] = 30 + (i % 100)
        for r in range(0, SIZE, 16):
            for c in range(0, SIZE, 16):
                if (r // 16 + c // 16) % 2 == 0:
                    arr[r : r + 16, c : c + 16] = min(255, 200 + (i % 55))
        Image.fromarray(arr).save(shoot / f"IMG_{4000 + i:04d}.png")

    print(f"Seeded {N_PHOTOS} photos into {shoot}")
    print("Next: photopicker-cull demo/shoot --top 10")


if __name__ == "__main__":
    main()
