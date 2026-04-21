"""Selector — orchestrates policy evaluation, eligibility checking, and capability resolution.

Selection flow (all steps after step 1 are optional based on injected dependencies):

    1.   PolicyEngine → (profile_name, rule_name)
    1.5  A/B experiment check (Phase 8) — deterministic percentage split
    1.7  Adaptive adjustment check (Phase 7) — redirect demoted profiles
    2.   Eligibility check against profile metadata
         - If ineligible, find the best eligible candidate (Phase 8: scored ranking)
    3.   CapabilityRegistry → downstream_model
    4.   Return SelectionResult with full trace populated

Eligibility rules (deterministic, config-driven via profiles.yaml):
    - requires_tools=True          AND  profile.supports_tools=False           → ineligible
    - requires_long_context=True   AND  profile.max_context_tokens < 16 000    → ineligible
    - requires_structured_output=True AND profile.supports_structured_output=False → ineligible

When the policy-selected profile is ineligible the selector tries candidates.
Phase 8 ranks candidates by multi-factor score (cost × sensitivity weights + quality + latency).
If nothing is eligible the original policy choice is used (fail-open).
"""

from __future__ import annotations

from typing import Any

from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult
from switchboard.observability.logging import get_logger
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.policy_engine import PolicyEngine

logger = get_logger(__name__)

# Preference order used as a tiebreaker when scorer produces equal totals.
_FALLBACK_PREFERENCE: tuple[str, ...] = ("capable", "fast", "default", "local")

# Context window below this is considered insufficient for long-context requests.
_MIN_LONG_CONTEXT_TOKENS = 16_000


class Selector:
    """Combines PolicyEngine + eligibility check + CapabilityRegistry → SelectionResult."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        capability_registry: CapabilityRegistry,
        profile_store=None,
        adjustment_store=None,
        experiment_router=None,
        profile_scorer=None,
    ) -> None:
        self._policy_engine = policy_engine
        self._capability_registry = capability_registry
        # Optional — enables eligibility validation against profile metadata.
        self._profile_store = profile_store
        # Optional — enables adaptive profile adjustment (Phase 7).
        self._adjustment_store = adjustment_store
        # Optional — enables A/B experiment routing (Phase 8).
        self._experiment_router = experiment_router
        # Optional — enables multi-factor candidate scoring (Phase 8).
        self._profile_scorer = profile_scorer

    def select(self, context: SelectionContext) -> SelectionResult:
        """Run the full selection pipeline and return a :class:`SelectionResult`.

        Raises:
            KeyError: If no eligible profile resolves and no model_hint fallback exists.
        """
        # 1. Policy evaluation → initial profile candidate
        profile_name, rule_name = self._policy_engine.select_profile(context)

        logger.debug(
            "Policy selected profile=%r via rule=%r for model_hint=%r",
            profile_name,
            rule_name,
            context.model_hint,
        )

        # 1.5 A/B experiment check (Phase 8)
        ab_experiment: str | None = None
        ab_bucket: str | None = None
        if self._experiment_router is not None:
            request_id = context.extra.get("request_id") or ""
            profile_name, ab_experiment, ab_bucket = self._experiment_router.route(
                profile_name, rule_name, request_id
            )
            if ab_experiment is not None:
                logger.info(
                    "A/B experiment=%r bucket=%r → profile=%r",
                    ab_experiment,
                    ab_bucket,
                    profile_name,
                )
                if ab_bucket == "B":
                    rule_name = f"experiment:{ab_experiment}"

        # 1.7 Adaptive adjustment check (Phase 7)
        adjustment_applied = False
        adjustment_reason: str | None = None
        if (
            self._adjustment_store is not None
            and self._adjustment_store.enabled
            and rule_name != "force_profile"
        ):
            adj = self._adjustment_store.get_adjustment(profile_name)
            if adj is not None and adj.action == "demote":
                alternative = self._find_non_demoted_profile(profile_name)
                if alternative is not None:
                    logger.info(
                        "Adaptive: demoting profile=%r (%s) → redirecting to profile=%r",
                        profile_name,
                        adj.reason,
                        alternative,
                    )
                    profile_name = alternative
                    rule_name = "adaptive_demote"
                    adjustment_applied = True
                    adjustment_reason = adj.reason

        # 2. Eligibility check (skipped when profile_store not injected)
        rejected: list[dict[str, Any]] = []
        scored_profiles: list[dict] | None = None
        if self._profile_store is not None and rule_name != "force_profile":
            eligible, rejection_reason = self._check_eligibility(profile_name, context)
            if not eligible:
                rejected.append({"profile": profile_name, "reason": rejection_reason})
                logger.warning(
                    "Profile %r rejected (%s) — finding eligible alternative",
                    profile_name,
                    rejection_reason,
                )
                profile_name, rule_name, scored_profiles = self._find_eligible_profile(
                    context, rejected
                )
                logger.info(
                    "Eligibility fallback selected profile=%r rule=%r",
                    profile_name,
                    rule_name,
                )

        # 3. Capability resolution → downstream model
        try:
            downstream_model = self._capability_registry.resolve_profile(profile_name)
        except KeyError:
            if context.model_hint:
                logger.warning(
                    "Profile %r not in capability registry; passing model_hint %r through.",
                    profile_name,
                    context.model_hint,
                )
                downstream_model = context.model_hint
                profile_name = "passthrough"
                rule_name = "passthrough_fallback"
            else:
                raise

        logger.debug("Resolved downstream_model=%r from profile=%r", downstream_model, profile_name)

        # 4. Cost estimate for trace
        cost_estimate = self._get_cost_estimate(profile_name)

        reason = _build_reason(profile_name, rule_name, rejected)

        return SelectionResult(
            profile=profile_name,
            profile_name=profile_name,
            downstream_model=downstream_model,
            rule_name=rule_name,
            reason=reason,
            rejected_profiles=rejected,
            context=context,
            adjustment_applied=adjustment_applied,
            adjustment_reason=adjustment_reason,
            cost_estimate=cost_estimate,
            ab_experiment=ab_experiment,
            ab_bucket=ab_bucket,
            scored_profiles=scored_profiles,
        )

    # ------------------------------------------------------------------
    # Adaptive helpers (Phase 7)
    # ------------------------------------------------------------------

    def _find_non_demoted_profile(self, demoted_profile: str) -> str | None:
        """Return the first preference-ordered profile that is not demoted."""
        known_profiles = set(self._capability_registry.all_profiles().keys())
        candidates = list(_FALLBACK_PREFERENCE) + sorted(
            p for p in known_profiles if p not in _FALLBACK_PREFERENCE
        )

        for candidate in candidates:
            if candidate == demoted_profile:
                continue
            if candidate not in known_profiles:
                continue
            adj = self._adjustment_store.get_adjustment(candidate)
            if adj is not None and adj.action == "demote":
                continue
            return candidate

        return None

    # ------------------------------------------------------------------
    # Eligibility helpers (Phase 3 + Phase 8)
    # ------------------------------------------------------------------

    def _check_eligibility(
        self,
        profile_name: str,
        context: SelectionContext,
    ) -> tuple[bool, str]:
        """Return ``(eligible, rejection_reason)`` for the given profile + context."""
        profiles = self._profile_store.get_profiles()
        meta = profiles.get(profile_name)
        if not isinstance(meta, dict):
            return True, ""

        if context.requires_tools and not meta.get("supports_tools", True):
            return False, "profile does not support tool use"

        if context.requires_long_context:
            max_ctx = meta.get("max_context_tokens", 128_000)
            if max_ctx < _MIN_LONG_CONTEXT_TOKENS:
                return (
                    False,
                    f"profile context window ({max_ctx:,} tokens) too small for long-context request",
                )

        # Phase 8: structured output capability check
        if context.requires_structured_output and not meta.get("supports_structured_output", True):
            return False, "profile does not support structured output"

        return True, ""

    def _find_eligible_profile(
        self,
        context: SelectionContext,
        rejected: list[dict[str, Any]],
    ) -> tuple[str, str, list[dict] | None]:
        """Find the best eligible profile using multi-factor scoring (Phase 8).

        Falls back to fixed preference order if no scorer is injected.
        Appends additionally rejected candidates to ``rejected`` (mutates in place).

        Returns:
            ``(profile_name, rule_name, scored_profiles | None)``
        """
        profiles = self._profile_store.get_profiles()
        rejected_names = {r["profile"] for r in rejected}

        candidate_order = list(_FALLBACK_PREFERENCE) + [
            p for p in sorted(profiles.keys()) if p not in _FALLBACK_PREFERENCE
        ]

        # Collect all eligible candidates first
        eligible_candidates: list[str] = []
        for candidate in candidate_order:
            if candidate in rejected_names or candidate not in profiles:
                continue
            eligible, reason = self._check_eligibility(candidate, context)
            if eligible:
                eligible_candidates.append(candidate)
            else:
                rejected.append({"profile": candidate, "reason": reason})
                rejected_names.add(candidate)

        if not eligible_candidates:
            logger.warning(
                "No eligible profile found; falling back to first rejected: %s",
                rejected[0]["profile"],
            )
            return rejected[0]["profile"], "eligibility_no_valid_candidate", None

        # Phase 8: score candidates if scorer is available
        scored_profiles: list[dict] | None = None
        if self._profile_scorer is not None:
            scores = self._profile_scorer.score_candidates(eligible_candidates, profiles, context)
            scored_profiles = [s.as_dict() for s in scores]
            best = scores[0].profile
            logger.info(
                "Multi-factor scoring selected profile=%r from candidates=%r",
                best,
                eligible_candidates,
            )
            return best, "eligibility_fallback", scored_profiles

        # Fallback: first in preference order
        return eligible_candidates[0], "eligibility_fallback", None

    # ------------------------------------------------------------------
    # Cost estimation (Phase 8)
    # ------------------------------------------------------------------

    def _get_cost_estimate(self, profile_name: str) -> float | None:
        """Return the relative cost weight for the selected profile, or None."""
        if self._profile_store is None:
            return None
        profiles = self._profile_store.get_profiles()
        meta = profiles.get(profile_name)
        if not isinstance(meta, dict):
            return None
        cost_weight = meta.get("cost_weight")
        if cost_weight is not None:
            return float(cost_weight)
        # Fall back to tier-based estimate
        tier = meta.get("cost_tier", "")
        return {"low": 1.0, "medium": 5.0, "high": 10.0}.get(tier)


# ---------------------------------------------------------------------------
# Reason string builder
# ---------------------------------------------------------------------------

def _build_reason(
    profile_name: str,
    rule_name: str,
    rejected: list[dict[str, Any]],
) -> str:
    base = f"rule:{rule_name} → profile:{profile_name}"
    if not rejected:
        return base
    rejections = "; ".join(f"{r['profile']} ({r['reason']})" for r in rejected)
    return f"{base} [rejected: {rejections}]"
