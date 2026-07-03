from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image

from .classifier import Classifier, ClipClassifier
from .exif import get_capture_time
from .profiles import Selection, get_profile

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


def _image_dimensions(path: Path) -> dict[str, int] | None:
    try:
        with Image.open(path) as img:
            w, h = img.size
    except Exception:
        return None
    return {"width": int(w), "height": int(h)}


@dataclass
class PhotoPick:
    profile: str
    selection: Selection
    source_folder: Path

    def summary(self) -> str:
        lines = [f"Profile: {self.profile}", f"Source: {self.source_folder}", ""]
        for category, paths in self.selection.categorized.items():
            lines.append(f"== {category} ({len(paths)}) ==")
            for p in paths:
                lines.append(f"  - {p.name}")
        rejects = self.selection.reject_counts()
        if rejects:
            lines.append("")
            lines.append("== rejected ==")
            for reason, count in rejects.items():
                lines.append(f"  - {reason}: {count}")
        return "\n".join(lines)

    def to_manifest(
        self,
        output_paths: dict[Path, Path] | None = None,
        thumbnails: dict[Path, dict[int, Path]] | None = None,
        webp_paths: dict[Path, Path] | None = None,
        thumbnails_webp: dict[Path, dict[int, Path]] | None = None,
    ) -> dict[str, Any]:
        """Structured record consumers can render directly.

        Emits per-pick metadata (rank within category, capture time, dimensions)
        so downstream galleries don't have to reparse filenames or re-open files.
        Reject *counts* are included; reject paths are not, to keep the manifest
        tight for shipping into web builds.

        When `output_paths` is provided (a source-path → resolved-output-path
        map, populated by the CLI when `--output` is set), each pick also
        carries `output_path` and `output_filename` — these are what the
        frontend gallery should reference, since HEIC inputs are transcoded to
        JPG on the way out.

        When `thumbnails` is provided (source-path → {width: thumbnail_path}),
        each pick gets a `thumbnails` map of width-string → filename. This
        drops straight into a `<picture>` srcset without any post-processing.

        `webp_paths` and `thumbnails_webp` add the same treatment for the WebP
        siblings written by the CLI's `--webp` flag. When present, each pick
        also carries `output_webp` / `output_webp_filename` / `thumbnails_webp`
        so the frontend can render:

            <picture>
              <source type="image/webp" srcset="...webp">
              <source type="image/jpeg" srcset="...jpg">
              <img src="output_filename">
            </picture>
        """
        output_paths = output_paths or {}
        thumbnails = thumbnails or {}
        webp_paths = webp_paths or {}
        thumbnails_webp = thumbnails_webp or {}
        picks: list[dict[str, Any]] = []
        for category, paths in self.selection.categorized.items():
            for rank, path in enumerate(paths, start=1):
                capture = get_capture_time(path)
                pick: dict[str, Any] = {
                    "category": category,
                    "rank": rank,
                    "filename": path.name,
                    "path": str(path),
                    "capture_time": capture.isoformat() if capture else None,
                    "dimensions": _image_dimensions(path),
                }
                resolved = output_paths.get(path)
                if resolved is not None:
                    pick["output_path"] = str(resolved)
                    pick["output_filename"] = resolved.name
                thumbs = thumbnails.get(path)
                if thumbs:
                    pick["thumbnails"] = {
                        str(width): thumb_path.name
                        for width, thumb_path in sorted(thumbs.items())
                    }
                webp_resolved = webp_paths.get(path)
                if webp_resolved is not None:
                    pick["output_webp"] = str(webp_resolved)
                    pick["output_webp_filename"] = webp_resolved.name
                webp_thumbs = thumbnails_webp.get(path)
                if webp_thumbs:
                    pick["thumbnails_webp"] = {
                        str(width): thumb_path.name
                        for width, thumb_path in sorted(webp_thumbs.items())
                    }
                picks.append(pick)
        return {
            "profile": self.profile,
            "source": str(self.source_folder),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "picks": picks,
            "reject_counts": self.selection.reject_counts(),
        }


def discover_images(folder: Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        raise NotADirectoryError(f"{folder} is not a directory")
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SUPPORTED_EXTS
    )


def pick_photos(
    folder: Path | str,
    profile_name: str,
    classifier: Classifier | None = None,
) -> PhotoPick:
    folder = Path(folder)
    profile = get_profile(profile_name)
    chosen_classifier: Classifier = classifier if classifier is not None else ClipClassifier()
    paths = discover_images(folder)
    selection = profile.select(paths, chosen_classifier)
    return PhotoPick(profile=profile_name, selection=selection, source_folder=folder)
