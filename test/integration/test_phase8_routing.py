"""Integration tests for Phase 8 advanced routing capabilities.

Tests:
  - Cost-aware routing: cost_estimate in decision trace
  - A/B experiment routing: deterministic bucket assignment, trace fields
  - Structured output eligibility: profiles without support are rejected
  - Multi-factor scoring: cost_sensitivity and latency_sensitivity affect selection
  - Decision record carries all Phase 8 fields
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from switchboard.domain.policy_rule import ExperimentConfig
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.experiment_router import ExperimentRouter
from switchboard.services.policy_engine import PolicyEngine
from switchboard.services.profile_scorer import ProfileScorer
from switchboard.services.selector import Selector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ctx(**kwargs) -> SelectionContext:
    defaults = {
        "messages": [{"role": "user", "content": "hello"}],
        "model_hint": "",
        "estimated_tokens": 10,
    }
    defaults.update(kwargs)
    return SelectionContext(**defaults)


def _make_selector(
    policy_profile: str = "capable",
    policy_rule: str = "default_rule",
    available_profiles: dict | None = None,
    with_scorer: bool = False,
    experiment_router: ExperimentRouter | None = None,
) -> Selector:
    policy_engine = MagicMock(spec=PolicyEngine)
    policy_engine.select_profile.return_value = (policy_profile, policy_rule)

    profiles = available_profiles or {
        "capable": {
            "supports_tools": True,
            "max_context_tokens": 128_000,
            "supports_structured_output": True,
            "cost_tier": "high",
            "cost_weight": 10.0,
            "quality_tier": "high",
            "latency_tier": "medium",
        },
        "fast": {
            "supports_tools": True,
            "max_context_tokens": 128_000,
            "supports_structured_output": True,
            "cost_tier": "low",
            "cost_weight": 1.0,
            "quality_tier": "medium",
            "latency_tier": "low",
        },
        "local": {
            "supports_tools": False,
            "max_context_tokens": 8192,
            "supports_structured_output": False,
            "cost_tier": "low",
            "cost_weight": 0.1,
            "quality_tier": "medium",
            "latency_tier": "medium",
        },
    }

    profile_store = MagicMock()
    profile_store.get_profiles.return_value = profiles

    capability_registry = MagicMock(spec=CapabilityRegistry)
    capability_registry.resolve_profile.side_effect = lambda p: profiles.get(p, {}).get(
        "downstream_model", f"model-{p}"
    )
    capability_registry.all_profiles.return_value = profiles

    scorer = ProfileScorer() if with_scorer else None

    return Selector(
        policy_engine,
        capability_registry,
        profile_store=profile_store,
        experiment_router=experiment_router,
        profile_scorer=scorer,
    )


# ---------------------------------------------------------------------------
# Cost awareness
# ---------------------------------------------------------------------------


class TestCostAwareness:
    def test_cost_estimate_populated_from_cost_weight(self) -> None:
        selector = _make_selector(policy_profile="capable")
        result = selector.select(_ctx())
        assert result.cost_estimate == pytest.approx(10.0)

    def test_cost_estimate_populated_from_cost_tier_fallback(self) -> None:
        profiles = {
            "capable": {
                "supports_tools": True,
                "max_context_tokens": 128_000,
                "supports_structured_output": True,
                "cost_tier": "high",
                # No cost_weight — falls back to tier
                "quality_tier": "high",
                "latency_tier": "medium",
            }
        }
        selector = _make_selector(policy_profile="capable", available_profiles=profiles)
        result = selector.select(_ctx())
        assert result.cost_estimate == pytest.approx(10.0)  # "high" tier → 10.0

    def test_cost_estimate_low_tier(self) -> None:
        selector = _make_selector(policy_profile="fast")
        result = selector.select(_ctx())
        assert result.cost_estimate == pytest.approx(1.0)

    def test_cost_estimate_in_selection_result_fields(self) -> None:
        result = SelectionResult(
            profile="fast",
            profile_name="fast",
            downstream_model="gpt-4o-mini",
            rule_name="test",
            reason="test",
            cost_estimate=1.0,
        )
        assert result.cost_estimate == 1.0

    def test_cost_estimate_carried_to_decision_record(self) -> None:
        from switchboard.services.decision_logger import make_decision_record

        ctx = _ctx()
        result = SelectionResult(
            profile="fast",
            profile_name="fast",
            downstream_model="gpt-4o-mini",
            rule_name="default_rule",
            reason="test",
            context=ctx,
            cost_estimate=1.0,
        )
        record = make_decision_record(result=result, original_model_hint="fast")
        assert record.cost_estimate == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# A/B experiment routing
# ---------------------------------------------------------------------------


class TestABExperimentRouting:
    def _router(self, split: int = 100) -> ExperimentRouter:
        exp = ExperimentConfig(
            name="test_exp",
            profile_a="capable",
            profile_b="fast",
            split_percent=split,
            enabled=True,
        )
        return ExperimentRouter([exp])

    def test_bucket_b_redirects_to_profile_b(self) -> None:
        selector = _make_selector(
            policy_profile="capable",
            experiment_router=self._router(split=100),
        )
        ctx = _ctx(extra={"request_id": "req-abc"})
        result = selector.select(ctx)
        assert result.profile_name == "fast"
        assert result.ab_experiment == "test_exp"
        assert result.ab_bucket == "B"
        assert result.rule_name == "experiment:test_exp"

    def test_bucket_a_stays_on_profile_a(self) -> None:
        selector = _make_selector(
            policy_profile="capable",
            experiment_router=self._router(split=0),
        )
        ctx = _ctx(extra={"request_id": "req-abc"})
        result = selector.select(ctx)
        assert result.profile_name == "capable"
        assert result.ab_experiment == "test_exp"
        assert result.ab_bucket == "A"

    def test_no_experiment_fields_when_no_router(self) -> None:
        selector = _make_selector(policy_profile="capable")
        result = selector.select(_ctx())
        assert result.ab_experiment is None
        assert result.ab_bucket is None

    def test_ab_fields_in_decision_record(self) -> None:
        from switchboard.services.decision_logger import make_decision_record

        ctx = _ctx(extra={"request_id": "req-1"})
        result = SelectionResult(
            profile="fast",
            profile_name="fast",
            downstream_model="gpt-4o-mini",
            rule_name="experiment:test_exp",
            reason="A/B",
            context=ctx,
            ab_experiment="test_exp",
            ab_bucket="B",
        )
        record = make_decision_record(result=result, original_model_hint="capable")
        assert record.ab_experiment == "test_exp"
        assert record.ab_bucket == "B"

    def test_ab_assignment_is_deterministic(self) -> None:
        router = self._router(split=50)
        selector = _make_selector(policy_profile="capable", experiment_router=router)
        results = [
            selector.select(_ctx(extra={"request_id": "req-stable"})).ab_bucket
            for _ in range(5)
        ]
        assert len(set(results)) == 1  # all same bucket


# ---------------------------------------------------------------------------
# Structured output capability filtering
# ---------------------------------------------------------------------------


class TestStructuredOutputFiltering:
    def test_local_profile_rejected_for_structured_output(self) -> None:
        # local does not support structured output
        selector = _make_selector(policy_profile="local", with_scorer=False)
        ctx = _ctx(requires_structured_output=True)
        result = selector.select(ctx)
        # local should be rejected; selector falls back to capable or fast
        assert result.profile_name != "local"
        assert any(r["profile"] == "local" for r in result.rejected_profiles)

    def test_capable_profile_not_rejected_for_structured_output(self) -> None:
        selector = _make_selector(policy_profile="capable")
        ctx = _ctx(requires_structured_output=True)
        result = selector.select(ctx)
        assert result.profile_name == "capable"
        assert result.rejected_profiles == []

    def test_no_structured_output_req_does_not_filter_local(self) -> None:
        selector = _make_selector(policy_profile="local")
        ctx = _ctx(requires_structured_output=False)
        result = selector.select(ctx)
        assert result.profile_name == "local"

    def test_structured_output_rejection_in_reason(self) -> None:
        selector = _make_selector(policy_profile="local")
        ctx = _ctx(requires_structured_output=True)
        result = selector.select(ctx)
        rejection = next(r for r in result.rejected_profiles if r["profile"] == "local")
        assert "structured output" in rejection["reason"]


# ---------------------------------------------------------------------------
# Multi-factor scoring in eligibility fallback
# ---------------------------------------------------------------------------


class TestMultiFactorScoring:
    def test_scorer_used_when_injected(self) -> None:
        # Start with local (ineligible for tools), falls back with scorer
        selector = _make_selector(
            policy_profile="local",
            with_scorer=True,
        )
        ctx = _ctx(requires_tools=True)
        result = selector.select(ctx)
        # local rejected; scorer picks from capable/fast
        assert result.profile_name in ("capable", "fast")
        assert result.scored_profiles is not None

    def test_cost_sensitivity_high_scorer_picks_fast(self) -> None:
        # local rejected (no tools), cost_sensitivity=high → scorer prefers fast over capable
        selector = _make_selector(policy_profile="local", with_scorer=True)
        ctx = _ctx(requires_tools=True, cost_sensitivity="high")
        result = selector.select(ctx)
        assert result.profile_name == "fast"

    def test_scored_profiles_field_in_result(self) -> None:
        selector = _make_selector(policy_profile="local", with_scorer=True)
        ctx = _ctx(requires_tools=True)
        result = selector.select(ctx)
        assert result.scored_profiles is not None
        assert len(result.scored_profiles) > 0
        # Each score entry has expected keys
        for entry in result.scored_profiles:
            assert "profile" in entry
            assert "total_score" in entry

    def test_no_scorer_uses_preference_order(self) -> None:
        # Without scorer, eligible candidates use fixed preference order
        # capable comes before fast in _FALLBACK_PREFERENCE
        selector = _make_selector(policy_profile="local", with_scorer=False)
        ctx = _ctx(requires_tools=True)
        result = selector.select(ctx)
        assert result.profile_name == "capable"  # first in preference order
        assert result.scored_profiles is None


# ---------------------------------------------------------------------------
# Decision record carries all Phase 8 fields
# ---------------------------------------------------------------------------


class TestPhase8DecisionRecord:
    def test_decision_record_phase8_fields_default(self) -> None:
        from switchboard.domain.decision_record import DecisionRecord

        record = DecisionRecord(
            timestamp="2024-01-01T00:00:00+00:00",
            selected_profile="fast",
            downstream_model="gpt-4o-mini",
            rule_name="default",
            reason="test",
        )
        assert record.cost_estimate is None
        assert record.ab_experiment is None
        assert record.ab_bucket is None
        assert record.scored_profiles is None

    def test_make_decision_record_carries_scored_profiles(self) -> None:
        from switchboard.services.decision_logger import make_decision_record

        ctx = _ctx()
        scored = [{"profile": "fast", "total_score": 0.9, "cost_score": 1.0, "quality_score": 0.5, "latency_score": 1.0}]
        result = SelectionResult(
            profile="fast",
            profile_name="fast",
            downstream_model="gpt-4o-mini",
            rule_name="eligibility_fallback",
            reason="test",
            context=ctx,
            scored_profiles=scored,
        )
        record = make_decision_record(result=result, original_model_hint="")
        assert record.scored_profiles == scored
