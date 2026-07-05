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
from .core import pick_photos
from .profiles import (
    ConfigError,
    build_from_config,
    list_profiles,
    register_profile,
)


@click.command()
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
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(result.summary())

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
        click.echo(f"[dry-run] Would copy: " + ", ".join(note_bits))
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


if __name__ == "__main__":
    main()
