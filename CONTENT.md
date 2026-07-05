# PhotoPicker — potential content angles

Kept per root CLAUDE.md rule: capture "worth filming for TikTok" moments as they land.

## 2026-07-05 — cull vertical

- **60-second demo** — split screen. Left: raw folder of 500 photos with iOS thumb-scroll pain. Right: `photopicker-cull ~/shoot --top 30 --prompt "best portfolio deck photos"` → local web UI, hammer K/X for 60 seconds, hit E, done. Payoff shot: 30 keepers in a folder in ~2 minutes total.
- **Before/after** — same client folder run through: (a) manually with the iOS Photos app, timed; (b) `photopicker-cull` timed. Both timestamped, real footage of the click-through.
- **"Why I built it" cut** — 15 seconds. "I take construction photos. iPhone gives me 500 blurry near-dupes. Nothing existed that handled HEIC, blurs, dupes, AND let me review in a browser. So I built it in a weekend."
- **AI-optional angle** — "Not everything needs AI. The blur/dupe/exposure pass is deterministic. Vision is a bonus layer. The tool works offline; the API call is opt-in."

## Followups (only after step 1 ships)

- If the tool gets any pull: a "how it works" thread — dedup via perceptual hash, sharpness via Laplacian variance, one Claude Vision call per survivor. All boring, all fast.
