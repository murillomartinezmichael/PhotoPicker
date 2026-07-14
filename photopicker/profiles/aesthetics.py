"""Declarative aesthetic-bonus rules shared by the site profiles.

Every site profile ranks photos the same way: a base quality score (sharpness +
exposure) multiplied up by a stack of CLIP-driven aesthetic bonuses ("warm wood
at golden hour", "crew on site", ...). Before this module each profile hand-wrote
that math twice — once to rank (`_combined`) and once to explain (`_contributions`
for CLI `--benchmark`). Two hand-written copies of the same sum is a latent lie:
add a rule to one and forget the other and the benchmark table cheerfully reports
a score the ranker never used.

Here the rules are data. `contributions()` is the single source of truth and
`combined()` is defined as its sum, so the table and the ranking cannot disagree.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .registry import RuleBreakdown


@dataclass(frozen=True)
class AestheticRule:
    """One bonus: a CLIP prompt, the weight it carries, and its benchmark name.

    `weight` is a fraction of base quality awarded at probability 1.0 — a 0.5
    rule that fires fully makes the photo score 1.5x its bare quality. Rules
    stack additively, so keep the weights of a profile summing to something
    sane (Aries: 0.97, Big7: 1.05) or a photo that trips every rule runs away
    with the ranking.
    """

    name: str
    label: str
    weight: float


class AestheticRules:
    """An ordered rule stack: turns per-label CLIP probabilities into a score."""

    def __init__(self, rules: list[AestheticRule]) -> None:
        self._rules = rules

    @property
    def rules(self) -> list[AestheticRule]:
        return list(self._rules)

    @property
    def labels(self) -> list[str]:
        """CLIP prompts to classify with — pass these to `classify_batch`."""
        return [rule.label for rule in self._rules]

    def contributions(
        self, quality: float, probs: Mapping[str, float]
    ) -> dict[str, float]:
        """Score *points* each rule adds on top of base quality.

        Rules that scored zero stay in the dict so `--benchmark` shows every rule
        the profile considered, not just the ones that hit.
        """
        return {
            rule.name: quality * rule.weight * probs.get(rule.label, 0.0)
            for rule in self._rules
        }

    def combined(self, quality: float, probs: Mapping[str, float]) -> float:
        """The score the profile ranks with: base quality + every bonus."""
        return quality + sum(self.contributions(quality, probs).values())

    def breakdown(self, quality: float, probs: Mapping[str, float]) -> RuleBreakdown:
        """Ranking score and its explanation in one object (`.total` is the score)."""
        return RuleBreakdown(
            quality=quality,
            contributions=self.contributions(quality, probs),
        )
