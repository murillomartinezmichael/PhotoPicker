from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .classifier import Classifier, ClipClassifier
from .profiles import Selection, get_profile

SUPPORTED_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}


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
        return "\n".join(lines)


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
