"""Selector — orchestrates policy evaluation, eligibility checking, and capability resolution.

Phase 3 adds capability eligibility validation between policy evaluation and model
resolution.  The flow is:

    1. PolicyEngine → (profile_name, rule_name)
    2. Eligibility check against profile metadata
       - If ineligible, find the next eligible candidate and record the rejection
    3. CapabilityRegistry → downstream_model
    4. Return SelectionResult with reason and rejection trace populated

Eligibility rules (deterministic, config-driven via profiles.yaml):
    - requires_tools=True  AND  profile.supports_tools=False  → ineligible
    - requires_long_context=True  AND  profile.max_context_tokens < 16 000  → ineligible

When the policy-selected profile is ineligible the selector tries candidates in
preference order: capable → fast → default → local → (remaining profiles).
If nothing is eligible the original policy choice is used (fail-open) and the
log records all rejections.
"""

from __future__ import annotations

from typing import Any

from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult
from switchboard.observability.logging import get_logger
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.policy_engine import PolicyEngine

logger = get_logger(__name__)

# Preference order when the policy-selected profile is ineligible.
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
    ) -> None:
        self._policy_engine = policy_engine
        self._capability_registry = capability_registry
        # Optional — when provided, enables eligibility validation against profile metadata.
        self._profile_store = profile_store

    def select(self, context: SelectionContext) -> SelectionResult:
        """Run policy evaluation, eligibility check, and capability resolution.

        Args:
            context: The :class:`SelectionContext` produced by the classifier.

        Returns:
            A :class:`SelectionResult` with ``profile``, ``profile_name``,
            ``downstream_model``, ``rule_name``, ``reason``, and
            ``rejected_profiles`` populated.

        Raises:
            KeyError: If no eligible profile resolves in the capability registry
                      and no model_hint fallback is available.
        """
        # 1. Policy evaluation → initial profile candidate
        profile_name, rule_name = self._policy_engine.select_profile(context)

        logger.debug(
            "Policy selected profile=%r via rule=%r for model_hint=%r",
            profile_name,
            rule_name,
            context.model_hint,
        )

        # 2. Eligibility check (skipped when profile_store not injected)
        rejected: list[dict[str, Any]] = []
        if self._profile_store is not None and rule_name != "force_profile":
            eligible, rejection_reason = self._check_eligibility(profile_name, context)
            if not eligible:
                rejected.append({"profile": profile_name, "reason": rejection_reason})
                logger.warning(
                    "Profile %r rejected (%s) — finding eligible alternative",
                    profile_name,
                    rejection_reason,
                )
                profile_name, rule_name = self._find_eligible_profile(context, rejected)
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

        reason = _build_reason(profile_name, rule_name, rejected)

        return SelectionResult(
            profile=profile_name,
            profile_name=profile_name,
            downstream_model=downstream_model,
            rule_name=rule_name,
            reason=reason,
            rejected_profiles=rejected,
            context=context,
        )

    # ------------------------------------------------------------------
    # Eligibility helpers
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

        return True, ""

    def _find_eligible_profile(
        self,
        context: SelectionContext,
        rejected: list[dict[str, Any]],
    ) -> tuple[str, str]:
        """Find the first eligible profile in preference order.

        Appends any additionally rejected candidates to ``rejected`` (mutates in place).
        Returns ``(profile_name, rule_name)`` of the first eligible candidate, or
        falls back to the first rejection entry (fail-open) if nothing is eligible.
        """
        profiles = self._profile_store.get_profiles()
        rejected_names = {r["profile"] for r in rejected}

        candidates = list(_FALLBACK_PREFERENCE) + [
            p for p in sorted(profiles.keys()) if p not in _FALLBACK_PREFERENCE
        ]

        for candidate in candidates:
            if candidate in rejected_names or candidate not in profiles:
                continue
            eligible, reason = self._check_eligibility(candidate, context)
            if eligible:
                return candidate, "eligibility_fallback"
            rejected.append({"profile": candidate, "reason": reason})
            rejected_names.add(candidate)

        # Nothing eligible — fail open to the original policy choice
        logger.warning(
            "No eligible profile found for context; falling back to first rejected: %s",
            rejected[0]["profile"],
        )
        return rejected[0]["profile"], "eligibility_no_valid_candidate"


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
