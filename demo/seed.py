"""Generate synthetic photos into `demo/shoot/` for the readme walkthrough.

Two-clicks-from-nothing: this file exists so someone who just cloned the repo
can `python demo/seed.py && photopicker-cull demo/shoot --top 10` and see it work
without touching a real camera roll.

The frames are fake landscapes (gradient sky, ground band, sun, dark
structures) rather than abstract test patterns, so the web UI's grid reads as
a photo shoot in screenshots. The pipeline still gets everything it needs:

- 9 scenes x 4 jittered variants -> perceptual-dedup clusters ("+N similar")
- 1 sharp one-off scene -> a keeper with no cluster badge
- 3 blurred one-off scenes -> real "blurry" rejects for --include-rejects
- per-pixel sensor noise -> Laplacian variance clears the sharpness gate

Net: 40 frames -> 10 keepers, 27 duplicates, 3 blurry.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

SIZE = 900
SCENES = 9  # clustered scenes, VARIANTS near-duplicates each
VARIANTS = 4
SINGLES_SHARP = [9]  # scene ids rendered once, kept sharp
SINGLES_BLURRED = [10, 11, 12]  # scene ids rendered once, blurred -> rejected


def _render(g: int, v: int, blur: bool, rng: np.random.Generator) -> Image.Image:
    """One fake landscape. Scene `g` fixes the composition; variant `v` jitters it."""
    # Luminance structure must differ scene-to-scene (perceptual dedup hashes
    # grayscale): horizon, brightness, sun and structures all swing wide on g.
    daylight = 0.5 + 0.5 * ((g * 41) % 100) / 100  # 0.5 (dusk) .. 1.0 (noon)
    sky_top = (110 + (g * 13) % 70, 150 + (g * 7) % 50, 200 + (g * 11) % 55)
    sky_bot = (200, 215, 230)
    ground = (60 + (g * 17) % 60, 110 + (g * 9) % 50, 55 + (g * 5) % 40)
    horizon = 240 + g * 42 + v * 4  # strictly spread so scenes never hash-collide

    arr = np.zeros((SIZE, SIZE, 3), dtype=np.float64)
    t = (np.arange(SIZE) / SIZE)[:, None]
    for c in range(3):
        arr[:, :, c] = sky_top[c] + (sky_bot[c] - sky_top[c]) * t
    arr[horizon:, :] = ground
    arr *= daylight

    sun_x = 60 + (g * 199) % 780 + v * 6
    sun_y = 60 + (g * 137) % max(horizon - 180, 60)
    yy, xx = np.ogrid[:SIZE, :SIZE]
    sun = (xx - sun_x) ** 2 + (yy - sun_y) ** 2 <= (35 + (g * 23) % 75) ** 2
    arr[sun] = (250, 245, 205)

    # Scene-unique tall silhouette (tower/trunk). Darkens a full column of the
    # 8x8 dedup hash, so no two scenes land within its 6-bit threshold.
    tx = (g * 311) % (SIZE - 160) + v * 5
    arr[40:horizon, tx : tx + 150] = (28, 26, 30)

    for k in range((g % 4) + 1):  # buildings / trees on the ground line
        w = 70 + ((g * 29 + k * 41) % 170)
        h = 100 + ((g * 19 + k * 61) % 220)
        x0 = (g * 131 + k * 227) % (SIZE - w)
        shade = 25 + (k * 25 + g * 7) % 70
        arr[max(horizon - h, 0) : horizon, x0 : x0 + w] = (shade, shade * 0.9, shade * 0.8)

    # Sensor noise is what gives the quality gate a sharpness signal to measure.
    arr += rng.normal(0, 7, arr.shape)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=6))
    return img


def main() -> None:
    root = Path(__file__).parent
    shoot = root / "shoot"
    if shoot.exists():
        shutil.rmtree(shoot)
    shoot.mkdir(parents=True)

    frames: list[tuple[int, int, bool]] = [
        (g, v, False) for g in range(SCENES) for v in range(VARIANTS)
    ]
    frames += [(g, 0, False) for g in SINGLES_SHARP]
    frames += [(g, 0, True) for g in SINGLES_BLURRED]

    for i, (g, v, blur) in enumerate(frames):
        rng = np.random.default_rng(1000 * g + v)  # deterministic per frame
        _render(g, v, blur, rng).save(shoot / f"IMG_{4000 + i:04d}.png")

    print(f"Seeded {len(frames)} photos into {shoot}")
    print("Next: photopicker-cull demo/shoot --top 10")


if __name__ == "__main__":
    main()
