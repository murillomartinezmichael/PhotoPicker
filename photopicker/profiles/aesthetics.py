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

#: Every rule name any profile has declared this process. Populated as the
#: profile modules import, so it is complete once `photopicker.profiles` has
#: been imported — which is what lets `set_weight_overrides` reject a typo
#: instead of silently tuning nothing.
_KNOWN_RULE_NAMES: set[str] = set()

#: Rule-name → weight, overriding the weight the profile hard-codes. Set by
#: CLI `--weight name=value` so a shoot can be re-tuned without a code edit;
#: empty in library use, where the profile's own weights stand.
_WEIGHT_OVERRIDES: dict[str, float] = {}


def known_rule_names() -> set[str]:
    """Names of every rule declared by an imported profile."""
    return set(_KNOWN_RULE_NAMES)


def weight_overrides() -> dict[str, float]:
    """The overrides currently in force."""
    return dict(_WEIGHT_OVERRIDES)


def set_weight_overrides(overrides: Mapping[str, float]) -> None:
    """Replace the active weight overrides.

    Raises ValueError on a name no imported profile declares (a typo would
    otherwise tune nothing at all and look like it worked) or on a negative
    weight (a rule may be switched off with 0.0, never made a penalty — the
    saturation math in `contributions` assumes non-negative bonuses).
    """
    unknown = sorted(set(overrides) - _KNOWN_RULE_NAMES)
    if unknown:
        known = ", ".join(sorted(_KNOWN_RULE_NAMES)) or "(none)"
        raise ValueError(
            f"unknown rule name(s): {', '.join(unknown)}. Known rules: {known}"
        )
    negative = sorted(name for name, w in overrides.items() if w < 0)
    if negative:
        raise ValueError(f"weights must be >= 0, got negative for: {', '.join(negative)}")
    _WEIGHT_OVERRIDES.clear()
    _WEIGHT_OVERRIDES.update(overrides)


def clear_weight_overrides() -> None:
    """Drop every override; profiles go back to their declared weights."""
    _WEIGHT_OVERRIDES.clear()


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
        _KNOWN_RULE_NAMES.update(rule.name for rule in rules)

    @property
    def max_bonus(self) -> float:
        return self._max_bonus

    @staticmethod
    def _weight(rule: AestheticRule) -> float:
        """The rule's weight, honouring an active `--weight` override."""
        return _WEIGHT_OVERRIDES.get(rule.name, rule.weight)

    @property
    def rules(self) -> list[AestheticRule]:
        return list(self._rules)

    @property
    def names(self) -> frozenset[str]:
        """Rule names in this stack — hand to `Profile(rule_names=...)`."""
        return frozenset(rule.name for rule in self._rules)

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
            rule.name: self._weight(rule) * probs.get(rule.label, 0.0)
            for rule in self._rules
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
