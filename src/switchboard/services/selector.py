"""Selector — orchestrates policy evaluation and capability resolution.

Section 9.3

The Selector is the central domain service.  It:
    1. Calls the PolicyEngine to determine which profile applies.
    2. Calls the CapabilityRegistry to resolve the profile to a concrete
       downstream model identifier.
    3. Returns a fully populated SelectionResult.

The Selector itself holds no mutable state — it delegates everything to its
injected collaborators, making it easy to unit test.
"""

from __future__ import annotations

from switchboard.domain.models import SelectionContext, SelectionResult
from switchboard.observability.logging import get_logger
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.policy_engine import PolicyEngine

logger = get_logger(__name__)


class Selector:
    """Combines PolicyEngine + CapabilityRegistry to produce a SelectionResult."""

    def __init__(
        self,
        policy_engine: PolicyEngine,
        capability_registry: CapabilityRegistry,
    ) -> None:
        self._policy_engine = policy_engine
        self._capability_registry = capability_registry

    def select(self, context: SelectionContext) -> SelectionResult:
        """Run policy evaluation and capability resolution.

        Args:
            context: The :class:`SelectionContext` produced by the classifier.

        Returns:
            A :class:`SelectionResult` with ``profile_name``, ``downstream_model``,
            and ``rule_name`` populated.

        Raises:
            KeyError: If the selected profile is not present in the capability registry.
        """
        # 1. Policy evaluation → profile name
        profile_name, rule_name = self._policy_engine.select_profile(context)

        logger.debug(
            "Policy selected profile=%r via rule=%r for model_hint=%r",
            profile_name,
            rule_name,
            context.model_hint,
        )

        # 2. Capability resolution → downstream model
        try:
            downstream_model = self._capability_registry.resolve_profile(profile_name)
        except KeyError:
            # If the policy selected a profile not in the registry, try the
            # model_hint from the context as a last resort (pass-through mode).
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

        logger.debug(
            "Resolved downstream_model=%r from profile=%r",
            downstream_model,
            profile_name,
        )

        return SelectionResult(
            profile_name=profile_name,
            downstream_model=downstream_model,
            rule_name=rule_name,
            context=context,
        )
