from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..classifier import Classifier


@dataclass
class RuleBreakdown:
    """Why one photo scored what it scored — the payload behind CLI `--benchmark`.

    `quality` is the base composite (sharpness + exposure). `contributions` maps
    a rule name to the *score points* that rule added on top of the base, so the
    numbers are directly comparable and sum cleanly:

        total = quality + sum(contributions.values())

    A profile with no aesthetic rules can emit `contributions={}` and still get a
    valid breakdown. Rules that fired at zero probability are kept (as 0.0) so the
    table shows every rule the profile considered, not just the ones that hit.
    """

    quality: float
    contributions: dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return self.quality + sum(self.contributions.values())


@dataclass
class Selection:
    categorized: dict[str, list[Path]] = field(default_factory=dict)
    rejected: dict[str, list[Path]] = field(default_factory=dict)
    explain: dict[Path, RuleBreakdown] = field(default_factory=dict)

    def all_picked(self) -> list[Path]:
        seen: set[Path] = set()
        out: list[Path] = []
        for paths in self.categorized.values():
            for p in paths:
                if p not in seen:
                    out.append(p)
                    seen.add(p)
        return out

    def reject_counts(self) -> dict[str, int]:
        return {reason: len(paths) for reason, paths in self.rejected.items() if paths}


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
