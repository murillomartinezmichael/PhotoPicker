# PhotoPicker DECISIONS

Durable choices — the "why we picked X over Y" ledger. Read this before proposing a rewrite.

## D-001 — Offline core; AI is opt-in (2026-07-05)

The cull pipeline (dedup + quality gate + composite score + top-N) runs with zero API keys, zero network. Claude Vision is a `[vision]` extra that surfaces via `--prompt "..."`. `--no-ai` is redundant to leaving `--prompt` unset but exists so the flag reads as intentional.

**Why:** demo-video framing + LAW #2 (money order wins). The tool has to work for someone who hasn't signed up for anything. AI is a taste layer, not a load-bearing dependency. Also: LAW #6 (never fake it) — the offline path is deterministic and testable without mocking a network.

**Alternatives considered:** CLIP-in-the-loop (already available via `[clip]` for themed profiles; too heavy for a general cull), local vision models (Ollama/LLaVA — too much install friction for the demo audience).

## D-002 — Web UI via stdlib http.server; no framework (2026-07-05)

The review UI is `photopicker/webui.py`: `ThreadingHTTPServer` + inlined HTML/CSS/JS. No FastAPI, no build step, no `static/` directory.

**Why:** the wheel ships the UI. `pip install photopicker` and `photopicker-cull FOLDER` are the only two steps. No dev-server story to maintain. Boring tech (LAW #5). Total UI code < 800 lines HTML+JS+CSS.

**Alternatives considered:** FastAPI + Vite (build step, extra deps), Tkinter/PySide (worse UX for photo grids, harder to record for demo).

## D-003 — Sharpest-per-cluster via score-then-dedup (2026-07-05)

Pipeline order: `twin-collapse → composite-score (one pass) → sort by score DESC → perceptual dedup (first-seen wins in sorted order) → quality gate → top N`. The score is computed for every survivor once and cached, then reused for both dedup priority and final rank.

**Why:** dedup based on first-seen order is wrong for a burst of near-identical shots — you want the sharpest, not the earliest. Sorting before dedup makes "first-seen" = "highest-scored" so the sharpest wins the cluster with no separate cluster-picking pass. One score pass, not two.

**Alternatives considered:** a two-pass approach (dedup by hash first, score survivors second) — cheaper by ~10% but drops sharper-but-later shots. Explicit cluster-then-pick — more code, no win.

## D-004 — Session state persists to `.photopicker-session.json` in source folder (2026-07-05)

The review session's decisions (keep/reject per candidate + history) are serialized to a JSON file inside the source folder on every decision. `--resume` reopens the last one.

**Why:** Ctrl+C mid-review must not lose an hour of clicks. Storing next to the photos means it moves with them and one folder = one session. LocalStorage was rejected because the UI ships on `127.0.0.1` and Michael sometimes runs multiple culls in parallel; scoping by folder is the natural boundary.

**Alternatives considered:** `~/.photopicker/sessions/<hash>.json` (harder to notice + clean up), SQLite (overkill for a review buffer).

## D-005 — Money code gets retry+backoff even when the SDK could do it (2026-07-05 — RUNG 1 HARDEN)

`photopicker/vision.py` wraps every Claude Vision call in an internal retry loop with exponential backoff, even though the `anthropic` SDK has its own retry knob. The internal loop handles transient network + rate-limit failures explicitly, logs each retry with attempt count + delay, and gives up after a bounded try count (default 3).

**Why:** LAW #7 (money code is sacred). A rerank over 100 photos is 100 API calls; a single unhandled 429 kills the batch and the partial spend is unaccounted. Explicit control also lets us surface a "Vision rate-limited, sleeping N sec" message in the CLI progress bar so a long session doesn't look hung. The SDK's built-in retry is not observable from our code and defaults are conservative.

**Alternatives considered:** trusting the SDK (opaque — hard to tune per user), forcing sequential calls with sleeps (kills parallelism), circuit-breaker over threshold (overkill for a one-shot CLI).
