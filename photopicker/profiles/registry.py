from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..classifier import Classifier


@dataclass
class Selection:
    categorized: dict[str, list[Path]] = field(default_factory=dict)

    def all_picked(self) -> list[Path]:
        seen: set[Path] = set()
        out: list[Path] = []
        for paths in self.categorized.values():
            for p in paths:
                if p not in seen:
                    out.append(p)
                    seen.add(p)
        return out


@dataclass
class Profile:
    name: str
    select: Callable[[list[Path], Classifier], Selection]


_REGISTRY: dict[str, Profile] = {}


def register_profile(profile: Profile) -> None:
    _REGISTRY[profile.name] = profile


def get_profile(name: str) -> Profile:
    if name not in _REGISTRY:
        raise KeyError(f"Unknown profile: {name!r}. Known: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_profiles() -> list[str]:
    return sorted(_REGISTRY)
