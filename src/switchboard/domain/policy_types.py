"""Policy domain types: PolicyRule and PolicyConfig.

These types describe the shape of a loaded policy configuration.  They are
populated by :class:`switchboard.adapters.file_policy_store.FilePolicyStore`
and consumed by :class:`switchboard.services.policy_engine.PolicyEngine`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class PolicyRule(BaseModel):
    """A single conditional routing rule.

    Rules are evaluated in ascending ``priority`` order (lower number = higher
    priority).  The first rule whose ``conditions`` all match the
    ``SelectionContext`` wins.

    Attributes:
        name:           Human-readable identifier used in decision records and logs.
        priority:       Evaluation order.  Lower values are evaluated first.
        profile:        Profile name to select when this rule matches.
        conditions:     Key/value pairs that must match fields on SelectionContext.
                        Keys correspond to SelectionContext attribute names;
                        values may be scalars or lists (list = "any of").
        description:    Optional human-readable explanation.
    """

    name: str
    priority: int = 100
    profile: str
    conditions: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class PolicyConfig(BaseModel):
    """Top-level policy configuration loaded from ``policy.yaml``.

    Attributes:
        version:    Schema version string for the policy file.
        fallback_profile:   Profile to use when no rule matches.
        rules:      Ordered list of :class:`PolicyRule` objects.
    """

    version: str = "1"
    fallback_profile: str = "default"
    rules: list[PolicyRule] = Field(default_factory=list)

    def sorted_rules(self) -> list[PolicyRule]:
        """Return rules sorted by ascending priority."""
        return sorted(self.rules, key=lambda r: r.priority)
