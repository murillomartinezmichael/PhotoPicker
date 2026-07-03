# ADR-0001: scikit-learn per-profile scoring, not a neural net

**Status:** Accepted
**Date:** 2026-07-03
**Author:** Michael Martinez
**Deciders:** Michael Martinez

## Context

PhotoPicker's job is to look at a folder of photos and pick the strongest N. The "strongest" definition depends on context — for Aries Outdoor Living, "strong" means good composition of a finished deck; for Big7 Construction, "strong" means clarity of the completed build; for a general default, "strong" means low-blur + good exposure + reasonable composition.

Three model families were on the table:

1. **Hand-engineered feature scoring** (scikit-learn friendly): compute per-image features (blur, exposure, edge density, dominant color histogram, aspect balance), combine into a weighted score, threshold + rank.
2. **Deep learning classifier** (PyTorch / TensorFlow): fine-tune a pretrained image model on a labeled dataset of "good" vs "bad" photos.
3. **Off-the-shelf commercial API** (Google Vision, AWS Rekognition): send each photo to the cloud, use their aesthetic-quality signal.

The training-data reality: Michael has *dozens* of labeled examples per client, not thousands. Deep learning on that data would overfit hard.

The explainability reality: when the picker rejects a photo David likes, David wants to know *why*. "The neural net said no" is a bad answer. "The blur score is 0.72, threshold is 0.60, and the composition score is below average" is a debuggable answer.

The cost reality: PhotoPicker runs on a laptop or in CI. No GPUs. No API bills.

## Decision

We will build PhotoPicker using **scikit-learn** for the scoring model, with **hand-engineered per-image features** (blur, exposure, saturation, edge density, composition metrics) combined via a **per-profile weighted-score linear model**. Profiles live in `profiles/*.json` — one per client aesthetic (aries, big7, default).

## Alternatives considered

### Deep learning classifier (ResNet fine-tune)
- **Pro:** Higher ceiling on subtle-quality signals. Standard modern approach.
- **Con:** Overfits on dozens of labeled examples. Requires GPU or long CPU training. Not explainable — can't tell David why a photo scored low.
- **Why not:** Both technical (overfitting) and human (explainability) — the same reason. Deep learning is the right tool for millions of labels, not dozens.

### Off-the-shelf commercial API (Google Vision Aesthetic Score)
- **Pro:** No model to train, no code to maintain.
- **Con:** Per-image API cost. Aesthetic model is one-size-fits-all — no per-client tuning. Requires internet at inference time (kills CI usability).
- **Why not:** No per-profile tunability. The whole point of PhotoPicker is that Aries and Big7 have different aesthetic bars; a shared cloud score fights that.

### Rule-based only (no ML at all)
- **Pro:** Zero training. Deterministic.
- **Con:** Weights are hand-tuned per profile with no data-driven feedback loop. Hard to add new features without re-hand-tuning.
- **Why not:** Halfway house. Scikit-learn on a linear model IS essentially rule-based scoring with a data-driven weight discovery — get the tuning "for free" from the small labeled dataset.

## Consequences

### Positive
- **Explainable rejections.** Every score decomposes into per-feature contributions. When David asks "why didn't you pick photo 47?", we show him the blur/exposure/composition breakdown.
- **Runs on a laptop** — no GPU, no API, no internet.
- **Per-profile tunability** — each client has their own weights.json. Aries can weight composition high; Big7 can weight technical clarity high; default can weight generic quality.
- **Small training data works.** Linear scoring on hand-engineered features generalizes from dozens of examples where deep learning would overfit.
- **36 tests passing** on the current implementation; CI green on GitHub Actions. The stability comes from the model simplicity.
- **Testable.** Each feature is a pure function of a numpy image array. Each scoring model is deterministic given the same inputs.

### Negative / trade-offs accepted
- **Ceiling is lower than deep learning.** A neural net given 100k labels would beat us on subtle-quality signals. Fine — we don't have 100k labels.
- **Hand-engineered features miss things.** Semantic content ("is this a finished deck vs. a work-in-progress framing shot?") is invisible to blur/exposure metrics. A profile can weight *around* it but not *see* it.
- **New profiles require domain judgment.** Adding a client means understanding their aesthetic well enough to set weights. Not a black-box drop-in.

### Neutral
- **Escape hatch:** if training data grows past ~1000 labeled photos per profile, a scikit-learn RandomForest is a natural next step, and a fine-tuned CNN after that. The feature engineering layer stays useful either way as pre-processing.

## References

- [`CLAUDE.md`](../../CLAUDE.md) — project rules
- [`../../photopicker/scoring.py`](../../photopicker/scoring.py) — the scoring engine (was originally `scoring/` dir; consolidated to a module)
- [`../../photopicker/features.py`](../../photopicker/features.py) — hand-engineered feature extractors
- [`../../profiles/`](../../profiles/) — per-client aesthetic profiles (aries, big7, default)
- [`../../tests/`](../../tests/) — 36 tests locking down feature + scoring behavior
- Related standard: [`../../../docs/TESTING_STANDARDS.md`](../../../docs/TESTING_STANDARDS.md) — testing pyramid PhotoPicker aims to satisfy
- Consumer: [`../../../AriesOutdoorLiving-V2/scripts/import_photos.py`](../../../AriesOutdoorLiving-V2/scripts/import_photos.py) — uses PhotoPicker as an installed package
