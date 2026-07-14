from __future__ import annotations

import json
import sys
from pathlib import Path

import click

from .cache import CachingClassifier
from .classifier import ClipClassifier, StubClassifier
from .convert import (
    DEFAULT_JPG_QUALITY,
    DEFAULT_WEBP_QUALITY,
    RENAME_SCHEMES,
    copy_or_transcode,
    generate_thumbnails,
    resolve_output_name,
    to_webp,
)
from .core import discover_images, pick_photos
from .culler import (
    DEFAULT_MIN_LONG_EDGE,
    DEFAULT_MIN_SHARPNESS,
    DEFAULT_TOP_N,
    SORT_MODES,
    cull,
)
from .profiles import (
    ConfigError,
    build_from_config,
    get_profile,
    list_profiles,
    register_profile,
    set_weight_overrides,
)


def _parse_weights(pairs: tuple[str, ...]) -> dict[str, float]:
    """Turn `--weight name=value` strings into a rule-name → weight mapping.

    Raises ValueError with a human-readable message on a malformed pair; the
    caller turns that into a clean exit rather than a traceback.
    """
    weights: dict[str, float] = {}
    for pair in pairs:
        name, sep, raw = pair.partition("=")
        if not sep or not name.strip():
            raise ValueError(f"--weight expects NAME=VALUE, got {pair!r}")
        try:
            weights[name.strip()] = float(raw)
        except ValueError:
            raise ValueError(f"--weight value must be a number, got {raw!r}") from None
    return weights


def _check_weights_apply(profile_name: str, weights: dict[str, float]) -> None:
    """Reject a `--weight` the *selected* profile can't honour.

    `set_weight_overrides` only knows the union of every rule name in the process,
    so `--profile aries --weight crew=1` (a big7 rule) or a `--weight` on a
    `--config` profile that declares no rules used to pass validation and then tune
    nothing — the run looked retuned and wasn't. Scope the check to the profile
    actually running.
    """
    declared = get_profile(profile_name).rule_names
    if not declared:
        raise ValueError(
            f"profile {profile_name!r} has no tunable rules, so --weight would do "
            "nothing. The 'aries' and 'big7' profiles ship rules; a --config "
            "profile gets them from a 'rules' key."
        )
    unknown = sorted(set(weights) - declared)
    if unknown:
        raise ValueError(
            f"profile {profile_name!r} declares no rule(s) named: {', '.join(unknown)}. "
            f"Its rules: {', '.join(sorted(declared))}"
        )


def _share(value: float, total: float) -> str:
    """Rule contribution as a share of the photo's total score.

    A total of zero (black / unreadable frame scored 0.0) would divide by zero.
    """
    return f"{value / total * 100:5.1f}%" if total else "    -"


def _benchmark_lines(result) -> list[str]:
    """Render per-rule score contributions for every picked photo.

    Answers "why did this photo win?" — the base quality score, then each
    aesthetic rule's contribution in score points and as a share of the total.
    Rules that fired at zero are still listed, so it's obvious which rules the
    profile *considered* versus which ones actually moved the ranking.
    """
    explain = result.selection.explain
    if not explain:
        return [
            "",
            "== benchmark ==",
            f"  Profile {result.profile!r} does not report per-rule contributions.",
        ]

    lines = ["", "== benchmark: score contributions =="]
    for category, paths in result.selection.categorized.items():
        for rank, path in enumerate(paths, start=1):
            breakdown = explain.get(path)
            if breakdown is None:
                continue
            total = breakdown.total
            lines.append(f"{category} #{rank}  {path.name}  total {total:.3f}")
            lines.append(
                f"    quality           {breakdown.quality:7.3f}  "
                f"{_share(breakdown.quality, total)}"
            )
            for rule, points in breakdown.contributions.items():
                lines.append(f"    + {rule:<15} {points:+7.3f}  {_share(points, total)}")
    return lines


def _print_profiles_and_exit(ctx, _param, value):
    if not value or ctx.resilient_parsing:
        return
    for name in list_profiles():
        click.echo(name)
    ctx.exit(0)


@click.command()
@click.option(
    "--list-profiles",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_profiles_and_exit,
    help="Print available profile names one per line and exit. Skips --folder validation.",
)
@click.option(
    "--folder", "-f",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Folder of input photos.",
)
@click.option(
    "--profile", "-p",
    type=str,
    default=None,
    help=(
        f"Profile name. Available: {list_profiles()}. "
        "Omit when --config is set (config's own name is used)."
    ),
)
@click.option(
    "--config", "config_path",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    default=None,
    help="Load a JSON profile config. Onboards new projects with no Python file.",
)
@click.option(
    "--output", "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="If set, copy picked files into this folder, organized by category.",
)
@click.option(
    "--cache", "cache_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Persist classifier scores to this JSON file. Re-runs on the same folder skip CLIP.",
)
@click.option(
    "--manifest", "manifest_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help="Write a structured JSON manifest (per-pick metadata) to this path.",
)
@click.option(
    "--convert-heic/--no-convert-heic",
    default=True,
    help="When copying to --output, transcode HEIC → JPG so browsers can render. Default on.",
)
@click.option(
    "--jpg-quality",
    type=click.IntRange(1, 100),
    default=DEFAULT_JPG_QUALITY,
    show_default=True,
    help="JPEG quality for HEIC → JPG transcoding.",
)
@click.option(
    "--rename-scheme",
    type=click.Choice(RENAME_SCHEMES),
    default="original",
    show_default=True,
    help=(
        "How to name copied files. 'original' keeps source names. "
        "'sequential' emits 01/02/... globally. 'category-rank' emits "
        "before-01/before-02/... — anonymizes client-facing galleries."
    ),
)
@click.option(
    "--thumbnails",
    type=str,
    default="",
    help=(
        "Comma-separated widths (e.g. '400,800,1200') for extra JPGs alongside "
        "each --output pick. Manifest exposes them as a width→filename map, ready "
        "for a <picture> srcset. Widths larger than the source are skipped."
    ),
)
@click.option(
    "--webp/--no-webp",
    default=False,
    help=(
        "Write .webp siblings alongside every JPG output (main + thumbnails). "
        "Manifest gains output_webp / thumbnails_webp for <source type=\"image/webp\">."
    ),
)
@click.option(
    "--webp-quality",
    type=click.IntRange(1, 100),
    default=DEFAULT_WEBP_QUALITY,
    show_default=True,
    help="WebP quality when --webp is set. 82 ~ visually equal to JPG 92.",
)
@click.option("--json-out", is_flag=True, help="Print result as JSON.")
@click.option(
    "--benchmark",
    is_flag=True,
    help=(
        "Show WHY each photo scored — base quality plus every profile rule's "
        "contribution in score points. Use it to tune profile weights. Profiles "
        "that report no breakdown (e.g. default) say so."
    ),
)
@click.option(
    "--weight",
    "weight_pairs",
    multiple=True,
    metavar="NAME=VALUE",
    help=(
        "Override a profile rule's weight for this run, e.g. "
        "--weight warmth=0.8 --weight furnished=0. Repeatable. Rule names are "
        "the ones --benchmark prints; 0 switches a rule off. Tune a shoot "
        "without editing the profile."
    ),
)
@click.option(
    "--dry-run",
    is_flag=True,
    help=(
        "Skip CLIP inference + skip writes to --output and --manifest. Uses "
        "StubClassifier so the pick step is nearly instant. Useful to sanity-"
        "check --profile / --config against a real folder before waiting on "
        "CLIP or committing to a copy."
    ),
)
def main(
    folder: Path,
    profile: str | None,
    config_path: Path | None,
    output: Path | None,
    cache_path: Path | None,
    manifest_path: Path | None,
    convert_heic: bool,
    jpg_quality: int,
    rename_scheme: str,
    thumbnails: str,
    webp: bool,
    webp_quality: int,
    json_out: bool,
    benchmark: bool,
    weight_pairs: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Pick the best photos from FOLDER using PROFILE."""
    if config_path is not None:
        try:
            with config_path.open("r", encoding="utf-8") as fh:
                cfg = json.load(fh)
        except (json.JSONDecodeError, OSError) as exc:
            click.echo(f"Failed to read config {config_path}: {exc}", err=True)
            sys.exit(1)
        try:
            built = build_from_config(cfg)
        except ConfigError as exc:
            click.echo(f"Invalid config: {exc}", err=True)
            sys.exit(1)
        register_profile(built)
        profile = profile or built.name

    if profile is None:
        click.echo("--profile is required unless --config is set", err=True)
        sys.exit(1)

    if profile not in list_profiles():
        click.echo(f"Unknown profile {profile!r}. Available: {list_profiles()}", err=True)
        sys.exit(1)

    if weight_pairs:
        try:
            weights = _parse_weights(weight_pairs)
            _check_weights_apply(profile, weights)
            set_weight_overrides(weights)
        except ValueError as exc:
            click.echo(f"Bad --weight: {exc}", err=True)
            sys.exit(1)

    thumb_widths: list[int] = []
    if thumbnails.strip():
        try:
            thumb_widths = sorted({int(w) for w in thumbnails.split(",") if w.strip()})
        except ValueError:
            click.echo(
                f"--thumbnails must be a comma-separated list of ints, got {thumbnails!r}",
                err=True,
            )
            sys.exit(1)
        if any(w <= 0 for w in thumb_widths):
            click.echo("--thumbnails widths must all be positive", err=True)
            sys.exit(1)

    if dry_run:
        # StubClassifier returns uniform scores so profiles that use
        # classify_batch fall back to per-image composite scoring alone. Fast
        # enough to iterate on --profile choice + --folder without waiting on
        # CLIP.
        classifier = StubClassifier()
    elif cache_path:
        classifier = CachingClassifier(ClipClassifier(), cache_path)
    else:
        classifier = None
    result = pick_photos(folder, profile, classifier=classifier)

    if dry_run:
        click.echo("[dry-run] CLIP skipped — pick shown below is StubClassifier-uniform.")

    if json_out:
        payload = {
            "profile": result.profile,
            "source": str(result.source_folder),
            "selection": {
                cat: [str(p) for p in paths]
                for cat, paths in result.selection.categorized.items()
            },
            "rejected": {
                reason: [str(p) for p in paths]
                for reason, paths in result.selection.rejected.items()
                if paths
            },
        }
        if benchmark:
            picked = set(result.selection.all_picked())
            payload["benchmark"] = {
                str(path): {
                    "quality": breakdown.quality,
                    "contributions": breakdown.contributions,
                    "total": breakdown.total,
                }
                for path, breakdown in result.selection.explain.items()
                if path in picked
            }
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(result.summary())
        if benchmark:
            click.echo("\n".join(_benchmark_lines(result)))

    output_paths: dict[Path, Path] = {}
    thumbnail_paths: dict[Path, dict[int, Path]] = {}
    webp_output_paths: dict[Path, Path] = {}
    thumbnail_webp_paths: dict[Path, dict[int, Path]] = {}
    if output and dry_run:
        total_picks = len(result.selection.all_picked())
        note_bits: list[str] = [f"{total_picks} photos → {output}"]
        if thumbnails.strip():
            note_bits.append(f"thumbnails at widths {thumbnails}")
        if webp:
            note_bits.append("webp siblings")
        if rename_scheme != "original":
            note_bits.append(f"rename via {rename_scheme}")
        click.echo("[dry-run] Would copy: " + ", ".join(note_bits))
    elif output:
        output.mkdir(parents=True, exist_ok=True)
        total_picks = len(result.selection.all_picked())
        transcoded = 0
        renamed = 0
        thumbs_written = 0
        webp_written = 0
        global_rank = 0
        for category, paths in result.selection.categorized.items():
            sub = output / category
            for rank_in_category, src in enumerate(paths, start=1):
                global_rank += 1
                target_name = resolve_output_name(
                    src,
                    category=category,
                    rank_in_category=rank_in_category,
                    global_rank=global_rank,
                    total_picks=total_picks,
                    scheme=rename_scheme,
                    convert_heic=convert_heic,
                )
                dest = copy_or_transcode(
                    src, sub, convert_heic, jpg_quality, target_name=target_name
                )
                output_paths[src] = dest
                if dest.suffix.lower() == ".jpg" and src.suffix.lower() != ".jpg":
                    transcoded += 1
                if dest.name != src.name:
                    renamed += 1
                if thumb_widths:
                    produced = generate_thumbnails(
                        source=dest,
                        dest_dir=sub,
                        base_stem=dest.stem,
                        widths=thumb_widths,
                    )
                    if produced:
                        thumbnail_paths[src] = produced
                        thumbs_written += len(produced)
                if webp:
                    webp_dest = sub / f"{dest.stem}.webp"
                    to_webp(dest, webp_dest, webp_quality)
                    webp_output_paths[src] = webp_dest
                    webp_written += 1
                    if thumb_widths:
                        webp_thumbs = generate_thumbnails(
                            source=dest,
                            dest_dir=sub,
                            base_stem=dest.stem,
                            widths=thumb_widths,
                            quality=webp_quality,
                            fmt="webp",
                        )
                        if webp_thumbs:
                            thumbnail_webp_paths[src] = webp_thumbs
                            webp_written += len(webp_thumbs)
        parts = [f"Copied {total_picks} photos to {output}"]
        note_bits: list[str] = []
        if transcoded:
            note_bits.append(f"{transcoded} transcoded to JPG")
        if rename_scheme != "original" and renamed:
            note_bits.append(f"renamed via {rename_scheme}")
        if thumbs_written:
            note_bits.append(f"{thumbs_written} thumbnails")
        if webp_written:
            note_bits.append(f"{webp_written} webp")
        if note_bits:
            parts[0] += " (" + ", ".join(note_bits) + ")"
        click.echo("\n" + parts[0])

    if manifest_path and dry_run:
        click.echo(f"[dry-run] Would write manifest to {manifest_path}")
    elif manifest_path:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with manifest_path.open("w", encoding="utf-8") as fh:
            json.dump(
                result.to_manifest(
                    output_paths=output_paths or None,
                    thumbnails=thumbnail_paths or None,
                    webp_paths=webp_output_paths or None,
                    thumbnails_webp=thumbnail_webp_paths or None,
                ),
                fh,
                indent=2,
                sort_keys=True,
            )
        click.echo(f"Wrote manifest to {manifest_path}")


@click.command(name="photopicker-cull")
@click.argument(
    "folder",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option(
    "--top", "top_n",
    type=click.IntRange(1, 5000),
    default=DEFAULT_TOP_N,
    show_default=True,
    help="Number of keepers to surface.",
)
@click.option(
    "--output", "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help=(
        "Copy keepers here without opening the UI. Skipped when --serve is on."
    ),
)
@click.option(
    "--serve/--no-serve",
    default=None,
    help=(
        "Open the local web UI to review + export. Defaults on unless "
        "--output is set."
    ),
)
@click.option(
    "--port",
    type=click.IntRange(1024, 65535),
    default=8765,
    show_default=True,
    help="Port for the web UI.",
)
@click.option(
    "--prompt",
    type=str,
    default=None,
    help=(
        "Optional: rerank keepers via Claude Vision against this prompt. "
        "Example: 'best deck photos for a portfolio'. Requires "
        "`pip install photopicker[vision]` and ANTHROPIC_API_KEY."
    ),
)
@click.option(
    "--no-ai",
    is_flag=True,
    help="Skip AI rerank even when --prompt is set. Offline core only.",
)
@click.option(
    "--ai-workers",
    type=click.IntRange(1, 16),
    default=4,
    show_default=True,
    help="Parallel Claude Vision requests when reranking.",
)
@click.option(
    "--ai-max-attempts",
    type=click.IntRange(1, 10),
    default=None,
    help=(
        "Retry each Vision call up to N times with exponential backoff on rate "
        "limits / transient failures. Env override: PHOTOPICKER_VISION_MAX_ATTEMPTS."
    ),
)
@click.option(
    "--sharpness",
    type=float,
    default=DEFAULT_MIN_SHARPNESS,
    show_default=True,
    help="Reject frames below this Laplacian-variance floor.",
)
@click.option(
    "--min-long-edge",
    type=int,
    default=DEFAULT_MIN_LONG_EDGE,
    show_default=True,
    help="Reject frames whose longer edge is below this many pixels.",
)
@click.option(
    "--sort",
    "sort_mode",
    type=click.Choice(SORT_MODES),
    default="score",
    show_default=True,
    help="Order keepers by score (default), EXIF capture-time, or filename.",
)
@click.option(
    "--include-rejects",
    is_flag=True,
    help=(
        "Also surface pipeline rejects (blurry / near-dupes / too-small) in the "
        "review UI so you can rescue false positives. Rejects are hidden by "
        "default in the grid but a filter chip toggles them on."
    ),
)
@click.option(
    "--resume",
    is_flag=True,
    help=(
        "If `.photopicker-session.json` already exists in FOLDER, skip the cull "
        "pipeline and reopen that session. Fast when you Ctrl+C'd out mid-review."
    ),
)
@click.option(
    "--manifest",
    "manifest_path",
    type=click.Path(dir_okay=False, path_type=Path),
    default=None,
    help=(
        "Write a JSON manifest of the cull result (per-keeper rank + score + "
        "capture time + optional AI score) to this path."
    ),
)
@click.option(
    "--overwrite/--no-overwrite",
    default=False,
    show_default=True,
    help=(
        "Allow --output to write into a folder that already has files. Off by "
        "default so a stray path doesn't clobber a prior export."
    ),
)
@click.option(
    "--live-progress/--no-live-progress",
    default=False,
    show_default=True,
    help=(
        "Boot the web UI FIRST and stream cull progress into it. Useful on "
        "500+ photo folders where the initial cull takes 10+ seconds."
    ),
)
@click.option(
    "--json-out",
    is_flag=True,
    help="Print the cull result as JSON and exit (still writes --output if set).",
)
def cull_main(
    folder: Path,
    top_n: int,
    output: Path | None,
    serve: bool | None,
    port: int,
    prompt: str | None,
    no_ai: bool,
    ai_workers: int,
    ai_max_attempts: int | None,
    sharpness: float,
    min_long_edge: int,
    sort_mode: str,
    include_rejects: bool,
    resume: bool,
    manifest_path: Path | None,
    overwrite: bool,
    live_progress: bool,
    json_out: bool,
) -> None:
    """Cull FOLDER down to the best --top N photos.

    Zero-config surface for the common case: point at a shoot, get keepers.
    The offline pipeline (dedup + quality gate + composite score) handles the
    technical pass; --prompt adds an optional Claude Vision rerank for taste.
    Default UX opens a local web UI where you keep/reject with K/X and export
    with one button.
    """
    paths = discover_images(folder)
    if not paths:
        click.echo(f"No supported images in {folder}", err=True)
        sys.exit(1)

    session_path = folder / ".photopicker-session.json"

    if resume and session_path.exists():
        if _resume_ui(folder, session_path, port):
            return
        # Malformed / mismatched session — clear it and fall through to a
        # fresh cull rather than bailing on the operator.
        click.echo(
            f"Session file {session_path.name} was unusable; falling through "
            "to a fresh cull.",
            err=True,
        )
        try:
            session_path.unlink()
        except OSError:
            pass

    effective_serve = serve if serve is not None else (output is None)
    if live_progress and effective_serve and not json_out:
        _run_live_progress_flow(
            folder=folder,
            paths=paths,
            top_n=top_n,
            sharpness=sharpness,
            min_long_edge=min_long_edge,
            sort_mode=sort_mode,
            prompt=prompt,
            no_ai=no_ai,
            ai_workers=ai_workers,
            ai_max_attempts=ai_max_attempts,
            include_rejects=include_rejects,
            session_path=session_path,
            port=port,
            manifest_path=manifest_path,
        )
        return

    def _progress(stage: str, done: int, total: int) -> None:
        if done in (0, total):
            click.echo(f"  {stage}: {done}/{total}", err=True)

    click.echo(f"Culling {len(paths)} -> top {top_n}...", err=True)
    result = cull(
        paths,
        top_n=top_n,
        min_sharpness=sharpness,
        min_long_edge=min_long_edge,
        sort=sort_mode,
        progress=_progress,
    )

    ai_scores: dict[Path, tuple[int, str]] = {}
    if prompt and not no_ai:
        try:
            from .vision import AnthropicVisionClient, rerank
        except ImportError as exc:  # pragma: no cover — depends on install layout
            click.echo(f"Could not load vision module: {exc}", err=True)
            sys.exit(1)
        def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            click.echo(
                f"  vision retry: {type(exc).__name__} on attempt {attempt}; "
                f"sleeping {delay:.1f}s",
                err=True,
            )

        try:
            client = AnthropicVisionClient(
                max_attempts=ai_max_attempts, on_retry=_on_retry
            )
        except RuntimeError as exc:
            click.echo(f"AI rerank unavailable: {exc}", err=True)
            sys.exit(1)
        click.echo(
            f"Claude Vision rerank on {len(result.keepers)} keepers "
            f"(prompt: {prompt!r})...",
            err=True,
        )

        def _ai_progress(done: int, total: int) -> None:
            if done in (0, total) or done % 10 == 0:
                click.echo(f"  vision: {done}/{total}", err=True)

        scores = rerank(
            result.keepers,
            prompt=prompt,
            client=client,
            max_workers=ai_workers,
            progress=_ai_progress,
        )
        # Reorder keepers by AI score, keep quality score for tie-break stability.
        ordered = [s.path for s in scores]
        result.keepers = ordered
        ai_scores = {s.path: (s.score, s.reason) for s in scores}

    if json_out:
        payload = {
            "folder": str(folder),
            "top": top_n,
            "keepers": [str(p) for p in result.keepers],
            "scores": {str(p): result.scores.get(p, 0.0) for p in result.keepers},
            "ai_scores": {
                str(p): {"score": s[0], "reason": s[1]}
                for p, s in ai_scores.items()
            },
            "reject_counts": result.reject_counts(),
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(result.summary())

    if output is not None and (serve is None or serve is False):
        if output.exists() and not overwrite:
            existing = [p for p in output.iterdir() if not p.name.startswith(".")]
            if existing:
                click.echo(
                    f"Refusing to write into non-empty folder {output} "
                    f"({len(existing)} entr{'y' if len(existing) == 1 else 'ies'} "
                    "found). Pass --overwrite to allow.",
                    err=True,
                )
                sys.exit(2)
        try:
            output.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            click.echo(f"Cannot create output folder {output}: {exc}", err=True)
            sys.exit(2)
        copied = 0
        for src in result.keepers:
            try:
                copy_or_transcode(src, output, convert_heic=True)
                copied += 1
            except OSError as exc:
                click.echo(f"  copy failed for {src.name}: {exc}", err=True)
        click.echo(f"\nCopied {copied}/{len(result.keepers)} keepers -> {output}", err=True)
        if copied == 0 and result.keepers:
            sys.exit(2)

    if manifest_path is not None:
        try:
            _write_manifest(
                manifest_path=manifest_path,
                folder=folder,
                top_n=top_n,
                prompt=prompt or "",
                result=result,
                ai_scores=ai_scores,
            )
        except OSError as exc:
            click.echo(f"Cannot write manifest {manifest_path}: {exc}", err=True)
            sys.exit(2)
        click.echo(f"Wrote manifest -> {manifest_path}", err=True)

    if serve is None:
        serve = output is None

    if serve:
        # Deferred import so `photopicker-cull --help` stays snappy.
        from .webui import SessionStore, build_session
        from .webui import serve as run_server

        rejected_map = result.rejected if include_rejects else None
        session = build_session(
            source_folder=folder,
            keepers=result.keepers,
            scores=result.scores,
            reject_summary=result.reject_counts(),
            input_count=result.total_input,
            prompt=prompt or "",
            ai_scores=ai_scores or None,
            include_rejects=rejected_map,
        )
        store = SessionStore(session=session, session_path=session_path)
        try:
            run_server(store, port=port)
        except OSError as exc:
            click.echo(f"Could not start server on port {port}: {exc}", err=True)
            sys.exit(1)


def _write_manifest(
    manifest_path: Path,
    folder: Path,
    top_n: int,
    prompt: str,
    result,
    ai_scores: dict,
) -> None:
    """Emit a JSON manifest so consumers can build a static gallery downstream.

    Fields per pick: rank, filename, path, score, ai_score/reason (when set),
    capture_time (ISO or null).
    """
    from datetime import datetime, timezone

    from .exif import get_capture_time

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    picks = []
    for rank, path in enumerate(result.keepers, start=1):
        capture = get_capture_time(path)
        entry = {
            "rank": rank,
            "filename": path.name,
            "path": str(path),
            "score": round(result.scores.get(path, 0.0), 4),
            "capture_time": capture.isoformat() if capture else None,
        }
        ai = ai_scores.get(path)
        if ai is not None:
            entry["ai_score"] = ai[0]
            entry["ai_reason"] = ai[1]
        picks.append(entry)
    payload = {
        "folder": str(folder),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "top": top_n,
        "prompt": prompt,
        "reject_counts": result.reject_counts(),
        "input_count": result.total_input,
        "picks": picks,
    }
    manifest_path.write_text(json.dumps(payload, indent=2))


def _run_live_progress_flow(
    *,
    folder: Path,
    paths: list[Path],
    top_n: int,
    sharpness: float,
    min_long_edge: int,
    sort_mode: str,
    prompt: str | None,
    no_ai: bool,
    ai_workers: int,
    ai_max_attempts: int | None,
    include_rejects: bool,
    session_path: Path,
    port: int,
    manifest_path: Path | None,
) -> None:
    """Live-progress flow: server FIRST, cull in a background thread.

    Browser opens the moment the socket binds; UI renders a progress screen
    from `/progress/stream`. Cull runs in a bg thread with a progress callback
    that feeds the broker. When cull finishes, the session store is hydrated
    with the real candidates and `broker.mark_finished()` flips the UI to the
    review grid.
    """
    import threading
    import time

    from .webui import (
        CullProgressBroker,
        SessionStore,
        build_session,
    )
    from .webui import serve as run_server

    empty_session = build_session(
        source_folder=folder,
        keepers=[],
        scores=None,
        reject_summary={},
        input_count=len(paths),
        prompt=prompt or "",
        ai_scores=None,
    )
    store = SessionStore(session=empty_session, session_path=session_path)
    broker = CullProgressBroker()
    broker.update("starting", 0, len(paths))

    server_thread = threading.Thread(
        target=run_server,
        kwargs={
            "store": store,
            "port": port,
            "open_browser": True,
            "progress": broker,
        },
        daemon=True,
        name="photopicker-webui",
    )
    server_thread.start()
    # Give the ThreadingHTTPServer a beat to bind before the cull kicks off.
    time.sleep(0.15)

    click.echo(
        f"Culling {len(paths)} -> top {top_n} (live progress in browser)...",
        err=True,
    )

    def _progress(stage: str, done: int, total: int) -> None:
        broker.update(stage, done, total)

    try:
        result = cull(
            paths,
            top_n=top_n,
            min_sharpness=sharpness,
            min_long_edge=min_long_edge,
            sort=sort_mode,
            progress=_progress,
        )
    except Exception as exc:  # unexpected — surface + finish broker so UI unblocks
        broker.update("error", 0, 0)
        broker.mark_finished()
        click.echo(f"Cull failed: {exc}", err=True)
        sys.exit(1)

    ai_scores: dict[Path, tuple[int, str]] = {}
    if prompt and not no_ai:
        try:
            from .vision import AnthropicVisionClient, rerank
        except ImportError as exc:  # pragma: no cover
            click.echo(f"Could not load vision module: {exc}", err=True)
            sys.exit(1)

        def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            click.echo(
                f"  vision retry: {type(exc).__name__} attempt {attempt}; "
                f"sleeping {delay:.1f}s",
                err=True,
            )

        try:
            client = AnthropicVisionClient(
                max_attempts=ai_max_attempts, on_retry=_on_retry
            )
        except RuntimeError as exc:
            click.echo(
                f"AI rerank unavailable: {exc}. Skipping vision pass; the "
                "offline cull result is still valid.",
                err=True,
            )
            client = None

        if client is not None:
            broker.update("vision", 0, len(result.keepers))

            def _ai_progress(done: int, total: int) -> None:
                broker.update("vision", done, total)

            try:
                scores = rerank(
                    result.keepers,
                    prompt=prompt,
                    client=client,
                    max_workers=ai_workers,
                    progress=_ai_progress,
                )
                result.keepers = [s.path for s in scores]
                ai_scores = {s.path: (s.score, s.reason) for s in scores}
            except Exception as exc:  # rerank shouldn't raise but be safe
                click.echo(
                    f"Vision rerank failed: {exc}. Falling back to offline "
                    "order.",
                    err=True,
                )

    # Hydrate the session store with the real candidates.
    rejected_map = result.rejected if include_rejects else None
    hydrated = build_session(
        source_folder=folder,
        keepers=result.keepers,
        scores=result.scores,
        reject_summary=result.reject_counts(),
        input_count=result.total_input,
        prompt=prompt or "",
        ai_scores=ai_scores or None,
        include_rejects=rejected_map,
    )
    store.hydrate(hydrated)
    broker.mark_finished()

    click.echo(result.summary())
    if manifest_path is not None:
        try:
            _write_manifest(
                manifest_path=manifest_path,
                folder=folder,
                top_n=top_n,
                prompt=prompt or "",
                result=result,
                ai_scores=ai_scores,
            )
            click.echo(f"Wrote manifest -> {manifest_path}", err=True)
        except OSError as exc:
            click.echo(f"Cannot write manifest {manifest_path}: {exc}", err=True)

    click.echo(
        "Cull complete. Review the grid in the browser. Ctrl+C when done.",
        err=True,
    )
    # Server thread is daemon — block main until interrupted.
    try:
        while server_thread.is_alive():
            server_thread.join(timeout=1.0)
    except KeyboardInterrupt:
        click.echo("\nExiting.", err=True)


def _resume_ui(folder: Path, session_path: Path, port: int) -> bool:
    """Reopen a saved session without re-running the pipeline.

    Returns True when the UI ran to completion, False when the session file
    was malformed / mismatched so the caller can drop through to a fresh cull
    instead of hard-exiting.
    """
    from .webui import Candidate, Session, SessionStore
    from .webui import serve as run_server

    try:
        raw = json.loads(session_path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        click.echo(
            f"Session file {session_path.name} was unreadable ({exc}).",
            err=True,
        )
        return False

    try:
        candidates = [Candidate(**c) for c in raw.get("candidates", [])]
    except TypeError as exc:
        # Newer session file has fields older Candidate doesn't accept, or
        # vice versa. Rather than crash, ignore it and let the caller cull fresh.
        click.echo(
            f"Session file {session_path.name} is from a different version "
            f"({exc}).",
            err=True,
        )
        return False

    if not candidates:
        click.echo(f"Session file {session_path.name} is empty.", err=True)
        return False

    click.echo(
        f"Resuming from {session_path.name} ({len(candidates)} candidates)...",
        err=True,
    )
    session = Session(
        source_folder=raw.get("source_folder", str(folder)),
        candidates=candidates,
        prompt=raw.get("prompt", ""),
        history=list(raw.get("history", [])),
        reject_summary=dict(raw.get("reject_summary", {})),
        input_count=int(raw.get("input_count", 0)),
    )
    store = SessionStore(session=session, session_path=session_path)
    try:
        run_server(store, port=port)
    except OSError as exc:
        click.echo(f"Could not start server on port {port}: {exc}", err=True)
        sys.exit(1)
    return True


if __name__ == "__main__":
    main()
