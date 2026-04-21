"""PolicyRule, ExperimentConfig, and PolicyConfig — policy domain types.

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
    priority).  The first rule whose ``when`` conditions all match the
    ``SelectionContext`` wins.

    Attributes:
        name:               Human-readable identifier used in decision records and logs.
        priority:           Evaluation order.  Lower values are evaluated first.
        select_profile:     Profile name to select when this rule matches.
        when:               Key/value pairs that must match fields on SelectionContext.
                            Keys correspond to SelectionContext attribute names;
                            values may be scalars or lists (list = "any of").
        description:        Optional human-readable explanation.
    """

    name: str
    priority: int = 100
    select_profile: str = ""
    when: dict[str, Any] = Field(default_factory=dict)
    description: str = ""

    # Legacy field — kept for backward-compat
    profile: str = ""
    conditions: dict[str, Any] = Field(default_factory=dict)

    @property
    def resolved_profile(self) -> str:
        """Return the profile name from either the new or legacy field."""
        return self.select_profile or self.profile

    @property
    def resolved_conditions(self) -> dict[str, Any]:
        """Return conditions from either the new ``when`` or legacy ``conditions`` field."""
        return self.when or self.conditions


class ExperimentConfig(BaseModel):
    """A controlled A/B routing experiment.

    Attributes:
        name:              Unique experiment identifier recorded in decision logs.
        profile_a:         Control profile (receives 100 - split_percent % of traffic).
        profile_b:         Treatment profile (receives split_percent % of traffic).
        split_percent:     Percentage of matching requests routed to ``profile_b`` (0–100).
        enabled:           Whether this experiment is active.
        applies_to_rules:  Rule names this experiment intercepts.
                           Empty list means "all rules except force_profile".
    """

    name: str
    profile_a: str
    profile_b: str
    split_percent: int = 10
    enabled: bool = True
    applies_to_rules: list[str] = Field(default_factory=list)


class PolicyConfig(BaseModel):
    """Top-level policy configuration loaded from ``policy.yaml``.

    Attributes:
        version:            Schema version string for the policy file.
        fallback_profile:   Profile to use when no rule matches.
        rules:              Ordered list of :class:`PolicyRule` objects.
    """

    version: str = "1"
    fallback_profile: str = "default"
    rules: list[PolicyRule] = Field(default_factory=list)
    experiments: list[ExperimentConfig] = Field(default_factory=list)

    def sorted_rules(self) -> list[PolicyRule]:
        """Return rules sorted by ascending priority."""
        return sorted(self.rules, key=lambda r: r.priority)
