"""PolicyEngine — evaluates ordered policy rules against a SelectionContext.

Section 9.2

The engine loads a :class:`PolicyConfig` from a :class:`PolicyStore` port and
evaluates rules in ascending priority order.  For each rule it checks every
condition key/value against the corresponding attribute on the context.

Condition matching semantics:
    - Scalar value: context attribute must equal the value.
    - List value: context attribute must be contained in the list (``any of``).
    - Special keys:
        ``min_estimated_tokens``: context.estimated_tokens >= value
        ``max_estimated_tokens``: context.estimated_tokens <= value
        ``min_max_tokens``: context.max_tokens >= value (if max_tokens is set)

Returns the profile name and rule name of the first matching rule.
Falls back to ``policy_config.fallback_profile`` with rule_name ``"fallback"``
if no rule matches.
"""

from __future__ import annotations

from typing import Any

from switchboard.domain.models import SelectionContext
from switchboard.domain.policy_types import PolicyConfig, PolicyRule
from switchboard.observability.logging import get_logger
from switchboard.ports.policy_store import PolicyStore

logger = get_logger(__name__)


class PolicyEngine:
    """Evaluates policy rules to select a profile for a given context."""

    def __init__(self, policy_store: PolicyStore) -> None:
        self._store = policy_store
        self._cached_config: PolicyConfig | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select_profile(self, context: SelectionContext) -> tuple[str, str]:
        """Evaluate policy rules and return ``(profile_name, rule_name)``.

        Args:
            context: The :class:`SelectionContext` to evaluate.

        Returns:
            A 2-tuple of ``(profile_name, rule_name)``.  ``rule_name`` is
            ``"force_profile"`` if a header override was present, the matched
            rule's name, or ``"fallback"`` if no rule matched.
        """
        # Header-based force override bypasses all rules
        if context.force_profile:
            logger.debug("Force profile override: %s", context.force_profile)
            return context.force_profile, "force_profile"

        config = self._get_config()

        for rule in config.sorted_rules():
            if self._rule_matches(rule, context):
                logger.debug("Rule matched: %s → profile %s", rule.name, rule.profile)
                return rule.profile, rule.name

        logger.debug("No rule matched; using fallback profile: %s", config.fallback_profile)
        return config.fallback_profile, "fallback"

    def reload(self) -> None:
        """Invalidate the cached policy config so it is reloaded on next request."""
        self._cached_config = None
        logger.info("Policy config cache invalidated")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_config(self) -> PolicyConfig:
        if self._cached_config is None:
            self._cached_config = self._store.get_policy()
            logger.info(
                "Policy loaded: %d rules, fallback=%s",
                len(self._cached_config.rules),
                self._cached_config.fallback_profile,
            )
        return self._cached_config

    @staticmethod
    def _rule_matches(rule: PolicyRule, context: SelectionContext) -> bool:
        """Return True if every condition in the rule is satisfied by the context."""
        for key, expected in rule.conditions.items():
            if not _condition_matches(key, expected, context):
                return False
        return True


# ---------------------------------------------------------------------------
# Condition matching helpers
# ---------------------------------------------------------------------------

def _condition_matches(key: str, expected: Any, context: SelectionContext) -> bool:
    """Check a single condition key/value pair against a context."""
    # Special numeric range conditions
    if key == "min_estimated_tokens":
        return context.estimated_tokens >= int(expected)
    if key == "max_estimated_tokens":
        return context.estimated_tokens <= int(expected)
    if key == "min_max_tokens":
        return context.max_tokens is not None and context.max_tokens >= int(expected)
    if key == "max_max_tokens":
        return context.max_tokens is not None and context.max_tokens <= int(expected)

    # General attribute matching
    actual = _get_context_value(key, context)

    if isinstance(expected, list):
        # "any of" semantics
        return actual in expected

    return actual == expected


def _get_context_value(key: str, context: SelectionContext) -> Any:
    """Extract a value from the context by key, falling back to the ``extra`` dict."""
    if hasattr(context, key):
        return getattr(context, key)
    return context.extra.get(key)
