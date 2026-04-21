"""Unit tests for ProfileScorer."""

from __future__ import annotations

import pytest

from switchboard.domain.selection_context import SelectionContext
from switchboard.services.profile_scorer import (
    ProfileScorer,
    _build_weights,
    _tier_to_cost_score,
    _tier_to_latency_score,
    _tier_to_quality_score,
)


def _ctx(**kwargs) -> SelectionContext:
    defaults = {
        "messages": [{"role": "user", "content": "hi"}],
        "model_hint": "",
    }
    defaults.update(kwargs)
    return SelectionContext(**defaults)


def _profiles() -> dict:
    return {
        "capable": {
            "cost_tier": "high",
            "cost_weight": 10.0,
            "quality_tier": "high",
            "latency_tier": "medium",
        },
        "fast": {
            "cost_tier": "low",
            "cost_weight": 1.0,
            "quality_tier": "medium",
            "latency_tier": "low",
        },
        "local": {
            "cost_tier": "low",
            "cost_weight": 0.1,
            "quality_tier": "medium",
            "latency_tier": "medium",
        },
    }


# ---------------------------------------------------------------------------
# Tier conversion helpers
# ---------------------------------------------------------------------------


class TestTierConversions:
    def test_cost_score_low_tier_is_highest(self) -> None:
        assert _tier_to_cost_score("low") > _tier_to_cost_score("medium") > _tier_to_cost_score("high")

    def test_quality_score_high_tier_is_highest(self) -> None:
        assert _tier_to_quality_score("high") > _tier_to_quality_score("medium") > _tier_to_quality_score("low")

    def test_latency_score_low_tier_is_highest(self) -> None:
        assert _tier_to_latency_score("low") > _tier_to_latency_score("medium") > _tier_to_latency_score("high")

    def test_unknown_tier_returns_mid_value(self) -> None:
        assert _tier_to_cost_score("unknown") == pytest.approx(0.5)
        assert _tier_to_quality_score("unknown") == pytest.approx(0.5)
        assert _tier_to_latency_score("unknown") == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Weight building
# ---------------------------------------------------------------------------


class TestBuildWeights:
    def test_default_weights_favour_quality(self) -> None:
        ctx = _ctx()
        w = _build_weights(ctx)
        assert w["quality"] >= w["cost"]

    def test_high_cost_sensitivity_raises_cost_weight(self) -> None:
        ctx = _ctx(cost_sensitivity="high")
        w = _build_weights(ctx)
        assert w["cost"] > w["quality"]

    def test_low_cost_sensitivity_lowers_cost_weight(self) -> None:
        ctx = _ctx(cost_sensitivity="low")
        w = _build_weights(ctx)
        assert w["quality"] > w["cost"]

    def test_high_latency_sensitivity_raises_latency_weight(self) -> None:
        ctx = _ctx(latency_sensitivity="high")
        w = _build_weights(ctx)
        assert w["latency"] > w["quality"]


# ---------------------------------------------------------------------------
# ProfileScorer.score_candidates
# ---------------------------------------------------------------------------


class TestProfileScorer:
    def setup_method(self) -> None:
        self.scorer = ProfileScorer()
        self.profiles = _profiles()

    def test_returns_one_score_per_candidate(self) -> None:
        ctx = _ctx()
        scores = self.scorer.score_candidates(["capable", "fast"], self.profiles, ctx)
        assert len(scores) == 2

    def test_sorted_by_total_score_descending(self) -> None:
        ctx = _ctx()
        scores = self.scorer.score_candidates(["capable", "fast", "local"], self.profiles, ctx)
        totals = [s.total_score for s in scores]
        assert totals == sorted(totals, reverse=True)

    def test_cost_sensitive_favours_cheap_profile(self) -> None:
        ctx = _ctx(cost_sensitivity="high")
        scores = self.scorer.score_candidates(["capable", "fast"], self.profiles, ctx)
        # fast has low cost → should score higher under cost_sensitivity=high
        assert scores[0].profile == "fast"

    def test_default_context_favours_quality_capable(self) -> None:
        ctx = _ctx()
        # With default weights (quality bias), capable should rank highly
        scores = self.scorer.score_candidates(["capable", "fast"], self.profiles, ctx)
        # capable has high quality_tier; fast has medium
        assert scores[0].profile == "capable"

    def test_latency_sensitive_favours_fast_profile(self) -> None:
        ctx = _ctx(latency_sensitivity="high")
        scores = self.scorer.score_candidates(["capable", "fast"], self.profiles, ctx)
        # fast has low latency_tier → should score higher
        assert scores[0].profile == "fast"

    def test_empty_candidates_returns_empty_list(self) -> None:
        ctx = _ctx()
        scores = self.scorer.score_candidates([], self.profiles, ctx)
        assert scores == []

    def test_unknown_profile_uses_defaults(self) -> None:
        ctx = _ctx()
        # Profile not in profiles dict — should still produce a score
        scores = self.scorer.score_candidates(["unknown_profile"], self.profiles, ctx)
        assert len(scores) == 1
        assert scores[0].profile == "unknown_profile"

    def test_as_dict_contains_expected_keys(self) -> None:
        ctx = _ctx()
        scores = self.scorer.score_candidates(["fast"], self.profiles, ctx)
        d = scores[0].as_dict()
        assert "profile" in d
        assert "cost_score" in d
        assert "quality_score" in d
        assert "latency_score" in d
        assert "total_score" in d

    def test_single_candidate_always_first(self) -> None:
        ctx = _ctx(cost_sensitivity="high")
        scores = self.scorer.score_candidates(["capable"], self.profiles, ctx)
        assert scores[0].profile == "capable"
