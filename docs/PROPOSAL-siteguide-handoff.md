# Proposal — SiteGuide handoff format (`--export siteguide`)

**Status:** Rung VII ENVISION — proposal, not built. Awaiting Mike's blessing before any code lands.
**Filed:** 2026-07-07 (fleet-all-day ignition · checkpoint 6)
**Chosen over:** the CockpitCloud fleet-preview panel candidate (see § "Why this over the other candidate").

---

## The one connective step

Add a single CLI flag to `photopicker-cull`:

```bash
photopicker-cull ./raw-shoot --top 30 --export siteguide --client aries
```

Produces one `aries-photos-2026-07-07.zip` bundle:

```
aries-photos-2026-07-07/
├── content/
│   └── gallery/
│       ├── deck-01.jpg
│       ├── deck-02.jpg
│       ...
├── content/gallery/manifest.json       ← keeper order + AI score + capture_time
└── README.txt                          ← 6-line client-facing note
```

The `content/gallery/` layout is exactly the shape Astro sites (CompanySite, AriesOutdoorLiving-V2, Big7Construction rebuild) drop images into. The zip unpacks straight over the site's tree; the site's next build picks up the new photos.

## Why this over the other candidate

The **CockpitCloud fleet-preview panel** (candidate #1 in `CHANGELOG.md § Envisioned`) is a nice-to-have — it makes Mike's kanban prettier. Real value: seeing "recent culls" without opening the folder.

**SiteGuide handoff** collapses the actual money path.

- **Aries client turnaround:** Mike does a job walkthrough → 200 raw photos → PhotoPicker cull → 30 keepers → upload to Aries site's gallery. Today: cull → manually rename → manually copy → git add → commit → push. **Afternoon of work.** With `--export siteguide`: cull → unzip → git commit. **Ten minutes.**
- **Big7 job cadence:** Big7's ADR-0001 explicitly parks "12 service-area + 7 offering pages" — one blocker is per-page photography. If PhotoPicker outputs the exact layout, the blocker becomes "shoot the photos" instead of "shoot + wrangle."
- **CompanySite case-study MP4s:** parked in TODO; same drop-in layout works.

Candidate #1 (Cockpit preview) can chain off #2 later (the manifest.json this proposal already writes → get read by Cockpit if the panel is built). Ship #2 first, #1 becomes a two-hour add-on.

## Wire shape (locked so Mike + a future agent can spec against it)

### CLI

```
--export FORMAT       New flag. FORMAT ∈ {siteguide, plain-zip}.
                      Default off. --export siteguide requires --client.
--client SLUG         Client identifier used in the folder + zip name.
                      Kebab-case; e.g. aries, big7, companysite.
                      Reused as the manifest.json:client field.
```

Any client slug matching an Aries V2 / Big7 / CompanySite content collection auto-picks the right sub-path. Unknown clients drop to `content/gallery/<slug>/`.

### Bundle layout (canonical)

```
<client>-photos-<YYYY-MM-DD>/
├── content/gallery/            ← Astro content-collection default
│   ├── <NN>-<slug>.jpg         ← sequence-numbered, safe filenames
│   ├── ...
│   └── manifest.json           ← the full pick metadata
└── README.txt                  ← 6 lines: unzip-into-site, git add, commit
```

Filename convention: `<sequence>-<slug>.jpg` where `sequence` is 2-digit zero-padded rank (`01`, `02`, ...) and `slug` is derived from EXIF capture date + optional AI-tag one-word summary. Falls back to `01-cull-2026-07-07.jpg` etc. when nothing to derive.

### manifest.json shape

Matches the existing `--manifest PATH` output (v0.12) plus a `client` field and a `bundle_created_at` field. **No new keys under existing keys** — that keeps the two manifests interchangeable.

```json
{
  "client": "aries",
  "bundle_created_at": "2026-07-07T04:55:00Z",
  "input_count": 217,
  "top_n": 30,
  "reject_counts": { "blurry": 42, "near_dupe": 88, "too_small": 3 },
  "picks": [
    {
      "rank": 1,
      "src": "IMG_4082.HEIC",
      "dst": "content/gallery/01-golden-hour-deck.jpg",
      "score": 0.94,
      "ai_score": 92,
      "ai_reason": "sharp golden-hour deck, low horizon, no faces",
      "capture_time": "2026-07-06T18:42:11-04:00"
    },
    ...
  ]
}
```

### README.txt (verbatim, 6 lines)

```
1. Unzip this file. You get a folder called content/.
2. Copy content/ into the top of your website's folder (overwrites nothing outside content/gallery/).
3. Open a terminal there. Type: git add content/gallery && git commit -m "photos: new cull" && git push
4. That's it. Your site rebuilds itself.
5. Questions: text Michael at [number].
6. — M³
```

Six lines because clients read exactly six lines. Any more gets skipped.

## Non-goals (say no now, don't rediscover later)

- **Not building a client web dashboard.** The bundle is inert. Clients unzip + push. No login, no upload UI, no state.
- **Not encrypting the zip.** Rights-clean photos → visitor site. No PII in the manifest either — filenames + scores only.
- **Not touching site build.** PhotoPicker outputs; site rebuild is the site's problem. Zero cross-repo dep.
- **Not converting HEIC → JPG in the bundle.** Existing `--output` copy path already does this via `photopicker.convert.copy_or_transcode`; we reuse it.

## Cost / effort

Rough sizing — proposal is doc-only, so this is only firing when Mike says GO.

- **1 checkpoint** — new `photopicker/exports/siteguide.py` (build_bundle + zip pack) + CLI flag wiring + 5-8 unit tests. Reuses existing convert + manifest paths.
- **1 checkpoint** — Docs pass on README.md + the demo/ walkthrough that includes a `--export siteguide --client demo` example.
- **0 new deps.** Python stdlib zipfile.

Two 90-minute movements, at most. Then the client-photo turnaround problem is gone.

## Rung II TEST plan (for the follow-up build)

- Golden-file test: fixture cull → export → unzip → assert directory shape matches the canonical layout above (byte-for-byte on README.txt).
- Manifest test: `client` field + `bundle_created_at` ISO-Z + all existing manifest v0.12 keys preserved.
- Filename-safety test: EXIF-derived slug can't produce `../` or Windows-invalid chars; fallback to sequence-only when derivation fails.
- Reject test: `--export siteguide` without `--client` errors cleanly + exits 2.
- Round-trip test: bundle a demo cull → unzip into a fresh Astro `content/gallery/` — Astro `content sync` reads it without errors (integration; only runs when Astro is installable in the test env; skip otherwise).

## Rung VII EVOLVE — the honest chain

This proposal IS the Rung VII step for PhotoPicker. If Mike accepts it and it builds:

1. **PhotoPicker Rung VIII RENEWAL** — mark cycle complete, return to Rung I HARDEN.
2. **CockpitCloud panel candidate** — no longer requires PhotoPicker touching the disk under `~/.cockpitcloud/`. The manifest.json produced by `--export siteguide` is already parseable. A CockpitCloud endpoint that scans a shared drop folder becomes a 30-minute chunk.
3. **AriesOutdoorLiving-V2 Day 8 R2 CDN migration** — already in Mike's queue. Aries's new gallery pipeline becomes: cull → export siteguide → the R2 uploader script (`scripts/upload_photos_to_r2.mjs` per memory) auto-mirrors the `content/gallery/` folder to the CDN.

The empire compounds when one afternoon of client work becomes 10 minutes and every subsequent client-photo project reuses the same one command.

---

**Answer, Mike, in one word: GO or PARK.**
