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
    stack additively up to the stack's `max_bonus` ceiling (see `AestheticRules`),
    so a profile can gain a rule without every earlier ranking inflating.
    """

    name: str
    label: str
    weight: float


#: Most a photo can gain from aesthetics, as a fraction of its base quality.
#: The bonuses exist to break ties between technically-sound photos, not to
#: promote a blurry one. At 0.75 a photo that trips every rule tops out at
#: 1.75x its bare quality, so a sharp, well-exposed shot with no aesthetic
#: signal still outranks a soft one that happens to be green, warm, and lit.
MAX_BONUS = 0.75


class AestheticRules:
    """An ordered rule stack: turns per-label CLIP probabilities into a score.

    Bonuses stack additively but *saturate*: once the summed weight-times-
    probability exceeds `max_bonus`, every rule's contribution is scaled down
    proportionally so the stack lands exactly on the ceiling. Two consequences
    worth knowing:

    - Ranking stays monotone — the bonus multiplier is `min(raw, max_bonus)`,
      which never reorders two photos that differ only in aesthetic strength.
    - Adding a rule is cheap. Without the cap, each new rule raised the ceiling
      for every photo already at the top, and aesthetics crept toward outweighing
      the sharpness/exposure score they were meant to merely tiebreak.
    """

    def __init__(
        self, rules: list[AestheticRule], max_bonus: float = MAX_BONUS
    ) -> None:
        self._rules = rules
        self._max_bonus = max_bonus

    @property
    def max_bonus(self) -> float:
        return self._max_bonus

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
        """Score *points* each rule adds on top of base quality, after saturation.

        Rules that scored zero stay in the dict so `--benchmark` shows every rule
        the profile considered, not just the ones that hit. When the stack
        saturates, the printed points are the scaled ones — the table always sums
        to the score the profile actually ranked with.
        """
        raw = {
            rule.name: rule.weight * probs.get(rule.label, 0.0) for rule in self._rules
        }
        earned = sum(raw.values())
        scale = self._max_bonus / earned if earned > self._max_bonus else 1.0
        return {name: quality * bonus * scale for name, bonus in raw.items()}

    def combined(self, quality: float, probs: Mapping[str, float]) -> float:
        """The score the profile ranks with: base quality + every bonus, capped."""
        return quality + sum(self.contributions(quality, probs).values())

    def breakdown(self, quality: float, probs: Mapping[str, float]) -> RuleBreakdown:
        """Ranking score and its explanation in one object (`.total` is the score)."""
        return RuleBreakdown(
            quality=quality,
            contributions=self.contributions(quality, probs),
        )
