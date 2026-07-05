# PhotoPicker demo

30-second walkthrough of `photopicker-cull`. Uses synthetic photos (procedurally
generated PNGs — no client work, no attribution, no rights headache) so anyone
can run it fresh without setting up an ANTHROPIC_API_KEY.

## Run it

```bash
# From the repo root:
python demo/seed.py                       # Generates 40 test photos in demo/shoot/
photopicker-cull demo/shoot --top 10      # Opens the web UI at http://127.0.0.1:8765
```

Then:

- Press **K** to keep, **X** to reject. Arrow keys navigate. `?` for the full key map.
- Press **E** and pick a target folder to copy the keepers.
- Ctrl+C to stop.

## Offline vs AI

`--no-ai` (default when `--prompt` is unset) stays entirely local — no API, no
key needed. The seeded photos won't wow Claude Vision (they're geometric
patterns) but you can still try:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
pip install "photopicker[vision]"
photopicker-cull demo/shoot --top 10 --prompt "high-contrast geometric patterns"
```

## What to record for the demo video

Recommended shot list (see `../CONTENT.md`):

1. `python demo/seed.py` — narrator: "40 photos in one command."
2. `photopicker-cull demo/shoot --top 10` — narrator: "Point at a folder, get keepers."
3. Fast-cut K/X presses in the UI.
4. Press E, type a target, one-button export.
5. Terminal shows `Copied 10 keepers -> ./demo/keepers`.

Total run time ≤ 60 seconds. Good for TikTok, YouTube Shorts, or a landing-page
demo GIF via `scripts/perf_1k.py --n 40 --keep`.
