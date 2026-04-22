"""
lane/engine.py — LaneSelector: TaskProposal → LaneDecision.

LaneSelector is the Phase 4 entry point for proposal-based routing. It
accepts a canonical TaskProposal, evaluates the LaneRoutingPolicy, and
produces a canonical LaneDecision with an attached DecisionExplanation.

Selection flow:
    1. Flatten proposal into a routing-signal dict
    2. Evaluate policy rules in priority order; first match wins
    3. Apply backend override rules (if any)
    4. Check excluded_backends
    5. Produce LaneDecision + DecisionExplanation
    6. Fall back to FallbackPolicy if no rule matched or all are excluded

SwitchBoard does not execute backends. It does not host models. It does not
external providers. It selects a lane and a backend and returns the decision.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from control_plane.contracts import LaneDecision, TaskProposal
from control_plane.contracts.enums import BackendName, LaneName

from .defaults import DEFAULT_POLICY
from .explain import DecisionExplanation, DecisionFactor
from .policy import LaneRoutingPolicy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lane universe known to this version of SwitchBoard
# ---------------------------------------------------------------------------

_KNOWN_LANES: frozenset[str] = frozenset(m.value for m in LaneName)
_KNOWN_BACKENDS: frozenset[str] = frozenset(m.value for m in BackendName)

class LaneSelector:
    """Selects an execution lane and backend for a canonical TaskProposal.

    Usage::

        selector = LaneSelector()                        # default policy
        selector = LaneSelector(policy=my_policy)        # custom policy

        decision = selector.select(proposal)
        explanation = selector.explain(proposal)
        issues = selector.validate_policy()
    """

    def __init__(self, policy: Optional[LaneRoutingPolicy] = None) -> None:
        self._policy = policy or DEFAULT_POLICY

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def select(self, proposal: TaskProposal) -> LaneDecision:
        """Evaluate routing policy and return a LaneDecision."""
        attrs = _proposal_attrs(proposal)
        lane, backend, rule_name, confidence, alternatives = self._evaluate_rules(attrs)

        rationale = self._build_rationale(lane, backend, rule_name, attrs)
        logger.debug(
            "LaneSelector: proposal=%s → lane=%s backend=%s rule=%s",
            proposal.proposal_id,
            lane,
            backend,
            rule_name,
        )

        return LaneDecision(
            proposal_id=proposal.proposal_id,
            selected_lane=LaneName(lane),
            selected_backend=BackendName(backend),
            confidence=confidence,
            policy_rule_matched=rule_name if rule_name != "fallback" else None,
            rationale=rationale,
            alternatives_considered=[
                LaneName(a) for a in alternatives if a in _KNOWN_LANES
            ],
            switchboard_version=_SWITCHBOARD_VERSION,
        )

    def explain(self, proposal: TaskProposal) -> DecisionExplanation:
        """Return a human-readable explanation of how the proposal would route."""
        attrs = _proposal_attrs(proposal)
        lane, backend, rule_name, confidence, alternatives = self._evaluate_rules(attrs)

        factors = _build_factors(attrs, lane, backend, rule_name)
        fallback_used = rule_name == "fallback"

        summary = (
            f"lane={lane}, backend={backend}, rule={rule_name}"
            if not fallback_used
            else f"lane={lane}, backend={backend} [fallback: no rule matched]"
        )

        return DecisionExplanation(
            rule_matched=rule_name if not fallback_used else None,
            factors=factors,
            alternatives_ruled_out=_ruled_out(attrs, lane, self._policy),
            fallback_used=fallback_used,
            fallback_recommendation=self._policy.fallback.lane if not fallback_used else None,
            summary=summary,
        )

    def plan_routes(self, proposal: "TaskProposal") -> "RoutingPlan":
        """Return a full RoutingPlan including fallback and escalation alternatives.

        Delegates to DecisionPlanner, which uses the same policy as this selector.
        Use this when callers need the complete picture of available alternatives,
        not just the primary route.
        """
        from .planner import DecisionPlanner
        from .routing import RoutingPlan
        planner = DecisionPlanner(policy=self._policy)
        return planner.plan(proposal)

    def validate_policy(self) -> list[str]:
        """Return a list of policy validation issues (empty = valid).

        Checks:
        - All rule select_lane values are in the known lane universe
        - All rule select_backend values are in the canonical backend universe
        - Fallback lane/backend are valid
        - No duplicate rule names
        """
        issues: list[str] = []
        valid_backends = _KNOWN_BACKENDS

        seen_names: set[str] = set()
        for rule in self._policy.rules:
            if rule.name in seen_names:
                issues.append(f"Duplicate rule name: '{rule.name}'")
            seen_names.add(rule.name)

            if rule.select_lane not in _KNOWN_LANES:
                issues.append(
                    f"Rule '{rule.name}': unknown lane '{rule.select_lane}'. "
                    f"Known: {sorted(_KNOWN_LANES)}"
                )
            if rule.select_backend not in valid_backends:
                issues.append(
                    f"Rule '{rule.name}': unknown backend '{rule.select_backend}'. "
                    f"Known: {sorted(valid_backends)}"
                )

        fb = self._policy.fallback
        if fb.lane not in _KNOWN_LANES:
            issues.append(f"Fallback lane '{fb.lane}' is not a known lane.")
        if fb.backend not in valid_backends:
            issues.append(f"Fallback backend '{fb.backend}' is not a known backend.")

        return issues

    # ------------------------------------------------------------------
    # Internal routing logic
    # ------------------------------------------------------------------

    def _evaluate_rules(
        self, attrs: dict[str, Any]
    ) -> tuple[str, str, str, float, list[str]]:
        """Evaluate policy rules and return (lane, backend, rule_name, confidence, alternatives).

        Falls back to FallbackPolicy when:
        - no rule matches, or
        - the selected backend is in excluded_backends.
        """
        excluded = set(self._policy.excluded_backends)
        alternatives: list[str] = []
        matched_rule = None

        for rule in self._policy.sorted_rules():
            if not rule.matches(attrs):
                continue
            if rule.select_backend in excluded:
                logger.debug(
                    "Rule '%s' matched but backend '%s' is excluded",
                    rule.name,
                    rule.select_backend,
                )
                alternatives.append(rule.select_lane)
                continue
            matched_rule = rule
            break

        if matched_rule is None:
            fb = self._policy.fallback
            return fb.lane, fb.backend, "fallback", 0.7, alternatives

        lane = matched_rule.select_lane
        backend = matched_rule.select_backend

        # Apply backend override rules
        for brule in self._policy.sorted_backend_rules():
            if brule.matches(lane, attrs):
                if brule.select_backend not in excluded:
                    backend = brule.select_backend
                    logger.debug(
                        "Backend override rule '%s' applied: %s → %s",
                        brule.name,
                        matched_rule.select_backend,
                        backend,
                    )
                break

        # Collect alternatives (other lanes from non-matching rules as candidates)
        for rule in self._policy.sorted_rules():
            if rule is matched_rule:
                continue
            if rule.select_lane != lane and rule.select_lane not in alternatives:
                alternatives.append(rule.select_lane)

        return lane, backend, matched_rule.name, matched_rule.confidence, alternatives

    def _build_rationale(
        self,
        lane: str,
        backend: str,
        rule_name: str,
        attrs: dict[str, Any],
    ) -> str:
        if rule_name == "fallback":
            return self._policy.fallback.rationale
        task_type = attrs.get("task_type", "unknown")
        risk = attrs.get("risk_level", "unknown")
        return (
            f"task_type={task_type}, risk_level={risk} → "
            f"lane={lane}, backend={backend} [rule: {rule_name}]"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SWITCHBOARD_VERSION = "0.4.0-phase4"


def _proposal_attrs(proposal: TaskProposal) -> dict[str, Any]:
    """Flatten a TaskProposal into a flat dict for rule matching."""
    return {
        "task_type": proposal.task_type.value,
        "execution_mode": proposal.execution_mode.value,
        "risk_level": proposal.risk_level.value,
        "priority": proposal.priority.value,
        "local_only": _is_local_only(proposal),
        "preferred_lane": _preferred_lane(proposal),
    }


def _is_local_only(proposal: TaskProposal) -> bool:
    """Return True if the proposal carries an explicit local-only label."""
    return "local_only" in proposal.labels


def _preferred_lane(proposal: TaskProposal) -> Optional[str]:
    """Extract preferred lane from labels (e.g. 'prefer:aider_local')."""
    for label in proposal.labels:
        if label.startswith("prefer:"):
            return label[len("prefer:"):]
    return None


def _build_factors(
    attrs: dict[str, Any],
    lane: str,
    backend: str,
    rule_name: str,
) -> list[DecisionFactor]:
    factors: list[DecisionFactor] = []
    for key in ("task_type", "risk_level", "priority", "execution_mode"):
        val = attrs.get(key)
        if val:
            factors.append(
                DecisionFactor(
                    name=key,
                    value=str(val),
                    influence="selected_lane" if key in ("task_type", "risk_level") else "confirmed_choice",
                )
            )
    if attrs.get("local_only"):
        factors.append(
            DecisionFactor(
                name="local_only",
                value="true",
                influence="selected_lane",
                note="Label 'local_only' forces aider_local lane.",
            )
        )
    return factors


def _ruled_out(attrs: dict[str, Any], selected_lane: str, policy: LaneRoutingPolicy) -> list[str]:
    """Return lanes that were candidates but not selected."""
    seen: set[str] = set()
    result: list[str] = []
    excluded = set(policy.excluded_backends)
    for rule in policy.sorted_rules():
        lane = rule.select_lane
        if lane == selected_lane or lane in seen:
            continue
        seen.add(lane)
        if rule.select_backend in excluded:
            result.append(f"{lane} (backend {rule.select_backend} excluded)")
        elif not rule.matches(attrs):
            result.append(f"{lane} (rule '{rule.name}' conditions not met)")
    return result
