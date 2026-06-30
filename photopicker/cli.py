from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import click

from .core import pick_photos
from .profiles import list_profiles


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
    required=True,
    help=f"Profile name. Available: {list_profiles()}",
)
@click.option(
    "--output", "-o",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="If set, copy picked files into this folder, organized by category.",
)
@click.option("--json-out", is_flag=True, help="Print result as JSON.")
def main(folder: Path, profile: str, output: Path | None, json_out: bool) -> None:
    """Pick the best photos from FOLDER using PROFILE."""
    if profile not in list_profiles():
        click.echo(f"Unknown profile {profile!r}. Available: {list_profiles()}", err=True)
        sys.exit(1)

    result = pick_photos(folder, profile)

    if json_out:
        payload = {
            "profile": result.profile,
            "source": str(result.source_folder),
            "selection": {
                cat: [str(p) for p in paths]
                for cat, paths in result.selection.categorized.items()
            },
        }
        click.echo(json.dumps(payload, indent=2))
    else:
        click.echo(result.summary())

    if output:
        output.mkdir(parents=True, exist_ok=True)
        for category, paths in result.selection.categorized.items():
            sub = output / category
            sub.mkdir(exist_ok=True)
            for src in paths:
                shutil.copy2(src, sub / src.name)
        click.echo(f"\nCopied {len(result.selection.all_picked())} photos to {output}")


if __name__ == "__main__":
    main()
