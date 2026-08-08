# PhotoPicker — potential content angles

Kept per master rules: capture "worth filming for TikTok" moments as they land.

## 2026-07-05 — v0.14 live progress

- **"Watch it work"** — 30s. Terminal: `photopicker-cull ~/big_shoot --top 30 --live-progress`. Browser opens instantly onto the cyan-glow progress screen. Bar fills: `scoring 45/500 → dedup 120/240 → quality-gate → vision`. Then snap-cut to the review grid. Narrator: "Every step, in real time. No blank tab, no lie."

## 2026-07-05 — v0.13 HARDEN cycle

- **"How I handle rate limits on a $0.007 API call"** — 30s. Show a fake 429 (`--ai-max-attempts`), narrate: "money code is sacred. Every call retries with backoff. If Claude says 429, I wait 2s, 4s, 8s — then move on. Never lose the batch."
- **"Port 8765 is busy — no problem"** — 15s. Terminal: `photopicker-cull demo/shoot` running twice in split panes. Right pane prints `port 8765 was busy; landed on 8766`. Narrator: "Boring tech. Boring UX. It just works."
- **"1000 photos in 17 seconds"** — 20s. `python scripts/perf_1k.py --n 1000` runs live. Timer overlay. Narrator: "One thousand photos, zero API keys, no cloud."
- **"Corrupt file? Not a crash."** — 20s. Drop a `not_an_image.jpg` (binary garbage) into the shoot folder. Cull runs, skips it, moves on. UI shows the broken file with a 500 badge instead of a stack trace. Narrator: "Software that respects your workflow."

## 2026-07-05 — v0.12 same-day follow-up

- **60-second demo** — split screen. Left: raw folder of 500 photos with iOS thumb-scroll pain. Right: `photopicker-cull ~/shoot --top 30 --prompt "best portfolio deck photos"` → local web UI, hammer K/X for 60 seconds, hit E, done. Payoff shot: 30 keepers in a folder in ~2 minutes total.
- **Before/after** — same client folder run through: (a) manually with the iOS Photos app, timed; (b) `photopicker-cull` timed. Both timestamped, real footage of the click-through.
- **"Why I built it" cut** — 15 seconds. "I take construction photos. iPhone gives me 500 blurry near-dupes. Nothing existed that handled HEIC, blurs, dupes, AND let me review in a browser. So I built it in a weekend."
- **AI-optional angle** — "Not everything needs AI. The blur/dupe/exposure pass is deterministic. Vision is a bonus layer. The tool works offline; the API call is opt-in."

## Followups (only after step 1 ships)

- If the tool gets any pull: a "how it works" thread — dedup via perceptual hash, sharpness via Laplacian variance, one Claude Vision call per survivor. All boring, all fast.

- `2026-08-03` — **Full IG short-form script drafted** (hook / demo beats / on-screen text / caption, grounded in this repo's real entry point, plus the demo hazards to avoid on camera): the fleet repo at `docs/content/IG_DRAFTS_2026-08-03.md` (this repo's section). Not filmed, not posted.
