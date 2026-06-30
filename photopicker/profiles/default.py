"""Default profile — top 9 by composite quality."""
from __future__ import annotations

from pathlib import Path

from ..classifier import Classifier
from ..scoring import composite_score
from .registry import Profile, Selection, register_profile

DEFAULT_TOP_N = 9


def make_select(top_n: int = DEFAULT_TOP_N):
    def select(paths: list[Path], classifier: Classifier) -> Selection:
        scored = [(p, composite_score(p)) for p in paths]
        scored.sort(key=lambda x: x[1], reverse=True)
        return Selection(categorized={"featured": [p for p, _ in scored[:top_n]]})

    return select


register_profile(Profile(name="default", select=make_select()))
