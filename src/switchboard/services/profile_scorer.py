"""ProfileScorer — multi-factor candidate ranking for eligibility fallback.

When the policy-selected profile is ineligible (or demoted), the Selector
needs to choose a replacement.  Phase 3 used a fixed preference order.
Phase 8 upgrades this to a scored ranking that considers:

  * cost     — from ``cost_tier`` in profiles.yaml; high cost_sensitivity = prefer cheap
  * quality  — from ``quality_tier`` in profiles.yaml; default weight favours quality
  * latency  — from ``latency_tier`` in profiles.yaml; high latency_sensitivity = prefer fast

All three dimensions produce a 0–1 score; higher is better.  The final
score is a weighted sum determined by context sensitivity flags.

Tier → numeric mapping (all three dimensions):
  low    → 1.0  (best: lowest cost / lowest latency / lowest quality)
  medium → 0.5
  high   → 0.0  (worst: highest cost / highest latency)

For cost and latency, a lower tier is *better*, so the score = 1.0 - tier_value.
For quality, a higher tier is *better*, so the score = tier_value directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from switchboard.domain.selection_context import SelectionContext


_TIER_TO_VALUE: dict[str, float] = {
    "low": 0.0,
    "medium": 0.5,
    "high": 1.0,
}

# Default scoring weights when the context has no explicit sensitivity set.
# Quality is weighted 4× so that high-quality profiles beat cheap+fast ones
# absent any explicit sensitivity signals from the caller.
_DEFAULT_WEIGHTS = {"quality": 4.0, "cost": 1.0, "latency": 1.0}


@dataclass
class ProfileScore:
    """Scored evaluation of a single profile candidate."""

    profile: str
    cost_score: float     # 0–1, higher = cheaper
    quality_score: float  # 0–1, higher = better quality
    latency_score: float  # 0–1, higher = lower latency
    total_score: float
    details: dict[str, float] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "cost_score": round(self.cost_score, 3),
            "quality_score": round(self.quality_score, 3),
            "latency_score": round(self.latency_score, 3),
            "total_score": round(self.total_score, 3),
        }


class ProfileScorer:
    """Score a list of candidate profiles using profile metadata and context sensitivity."""

    def score_candidates(
        self,
        candidates: list[str],
        profiles: dict[str, Any],  # profile_name → profile metadata dict
        context: SelectionContext,
    ) -> list[ProfileScore]:
        """Return candidates sorted by descending total score.

        Args:
            candidates: Profile names to score (already filtered for eligibility).
            profiles:   Profile metadata dict from FileProfileStore.
            context:    Current request context (provides sensitivity signals).

        Returns:
            List of :class:`ProfileScore` sorted by ``total_score`` descending.
        """
        weights = _build_weights(context)
        scored: list[ProfileScore] = []

        for profile in candidates:
            meta = profiles.get(profile, {})
            cost_score = _tier_to_cost_score(meta.get("cost_tier", "medium"))
            quality_score = _tier_to_quality_score(meta.get("quality_tier", "medium"))
            latency_score = _tier_to_latency_score(meta.get("latency_tier", "medium"))

            total = (
                weights["cost"] * cost_score
                + weights["quality"] * quality_score
                + weights["latency"] * latency_score
            )
            scored.append(
                ProfileScore(
                    profile=profile,
                    cost_score=cost_score,
                    quality_score=quality_score,
                    latency_score=latency_score,
                    total_score=total,
                )
            )

        scored.sort(key=lambda s: s.total_score, reverse=True)
        return scored


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_weights(context: SelectionContext) -> dict[str, float]:
    """Return scoring weights adjusted for context sensitivity signals."""
    weights = dict(_DEFAULT_WEIGHTS)
    if context.cost_sensitivity == "high":
        weights["cost"] = 4.0
        weights["quality"] = 1.0
    elif context.cost_sensitivity == "low":
        weights["cost"] = 0.5
        weights["quality"] = 3.0
    if context.latency_sensitivity == "high":
        weights["latency"] = 6.0  # must exceed default quality weight of 4.0
    elif context.latency_sensitivity == "low":
        weights["latency"] = 0.5
    return weights


def _tier_to_cost_score(tier: str) -> float:
    """Lower cost tier = higher score (we want cheap profiles to score well)."""
    return 1.0 - _TIER_TO_VALUE.get(tier, 0.5)


def _tier_to_quality_score(tier: str) -> float:
    """Higher quality tier = higher score."""
    return _TIER_TO_VALUE.get(tier, 0.5)


def _tier_to_latency_score(tier: str) -> float:
    """Lower latency tier = higher score (fast response is better)."""
    return 1.0 - _TIER_TO_VALUE.get(tier, 0.5)
