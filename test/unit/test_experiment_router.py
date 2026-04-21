"""Unit tests for ExperimentRouter."""

from __future__ import annotations

import pytest

from switchboard.domain.policy_rule import ExperimentConfig
from switchboard.services.experiment_router import ExperimentRouter, _assign_bucket


# ---------------------------------------------------------------------------
# Bucket assignment — determinism and distribution
# ---------------------------------------------------------------------------


class TestAssignBucket:
    def test_deterministic_for_same_inputs(self) -> None:
        b1 = _assign_bucket("req-abc", "exp-1", 50)
        b2 = _assign_bucket("req-abc", "exp-1", 50)
        assert b1 == b2

    def test_different_request_ids_may_differ(self) -> None:
        buckets = {_assign_bucket(f"req-{i}", "exp-1", 50) for i in range(100)}
        assert len(buckets) == 2  # must produce both A and B across 100 requests

    def test_split_0_always_a(self) -> None:
        for i in range(20):
            assert _assign_bucket(f"req-{i}", "exp-1", 0) == "A"

    def test_split_100_always_b(self) -> None:
        for i in range(20):
            assert _assign_bucket(f"req-{i}", "exp-1", 100) == "B"

    def test_approximate_50_50_split(self) -> None:
        b_count = sum(1 for i in range(1000) if _assign_bucket(f"req-{i}", "exp", 50) == "B")
        # Expect roughly 50% ± 10%
        assert 400 <= b_count <= 600

    def test_approximate_10_pct_split(self) -> None:
        b_count = sum(1 for i in range(1000) if _assign_bucket(f"req-{i}", "exp", 10) == "B")
        # Expect roughly 10% ± 5%
        assert 50 <= b_count <= 150


# ---------------------------------------------------------------------------
# ExperimentRouter
# ---------------------------------------------------------------------------


def _exp(
    name: str = "test_exp",
    profile_a: str = "capable",
    profile_b: str = "fast",
    split_percent: int = 100,  # 100% → always B for easy testing
    enabled: bool = True,
    applies_to_rules: list[str] | None = None,
) -> ExperimentConfig:
    return ExperimentConfig(
        name=name,
        profile_a=profile_a,
        profile_b=profile_b,
        split_percent=split_percent,
        enabled=enabled,
        applies_to_rules=applies_to_rules or [],
    )


class TestExperimentRouter:
    def test_no_experiments_returns_original_profile(self) -> None:
        router = ExperimentRouter([])
        profile, exp_name, bucket = router.route("capable", "some_rule", "req-1")
        assert profile == "capable"
        assert exp_name is None
        assert bucket is None

    def test_force_profile_never_intercepted(self) -> None:
        router = ExperimentRouter([_exp(profile_a="capable")])
        profile, exp_name, bucket = router.route("capable", "force_profile", "req-1")
        assert profile == "capable"
        assert exp_name is None

    def test_routes_to_b_when_split_100(self) -> None:
        router = ExperimentRouter([_exp(profile_a="capable", profile_b="fast", split_percent=100)])
        profile, exp_name, bucket = router.route("capable", "default_rule", "req-1")
        assert profile == "fast"
        assert exp_name == "test_exp"
        assert bucket == "B"

    def test_stays_on_a_when_split_0(self) -> None:
        router = ExperimentRouter([_exp(profile_a="capable", profile_b="fast", split_percent=0)])
        profile, exp_name, bucket = router.route("capable", "default_rule", "req-1")
        assert profile == "capable"
        assert exp_name == "test_exp"
        assert bucket == "A"

    def test_disabled_experiment_is_ignored(self) -> None:
        router = ExperimentRouter([_exp(split_percent=100, enabled=False)])
        profile, exp_name, bucket = router.route("capable", "default_rule", "req-1")
        assert profile == "capable"
        assert exp_name is None

    def test_experiment_skipped_when_profile_a_does_not_match(self) -> None:
        router = ExperimentRouter([_exp(profile_a="capable", split_percent=100)])
        profile, exp_name, bucket = router.route("fast", "default_rule", "req-1")
        assert profile == "fast"
        assert exp_name is None

    def test_applies_to_rules_restricts_matching(self) -> None:
        router = ExperimentRouter(
            [_exp(split_percent=100, applies_to_rules=["target_rule"])]
        )
        # Rule does not match
        profile, exp_name, bucket = router.route("capable", "other_rule", "req-1")
        assert profile == "capable"
        assert exp_name is None

    def test_applies_to_rules_matches_when_rule_listed(self) -> None:
        router = ExperimentRouter(
            [_exp(split_percent=100, applies_to_rules=["target_rule"])]
        )
        profile, exp_name, bucket = router.route("capable", "target_rule", "req-1")
        assert profile == "fast"
        assert bucket == "B"

    def test_first_matching_experiment_wins(self) -> None:
        router = ExperimentRouter([
            _exp(name="exp_a", profile_a="capable", profile_b="fast", split_percent=100),
            _exp(name="exp_b", profile_a="capable", profile_b="local", split_percent=100),
        ])
        profile, exp_name, bucket = router.route("capable", "rule", "req-1")
        assert profile == "fast"  # first experiment wins
        assert exp_name == "exp_a"

    def test_active_experiments_property(self) -> None:
        router = ExperimentRouter([_exp(enabled=True), _exp(name="disabled", enabled=False)])
        assert len(router.active_experiments) == 1
        assert router.active_experiments[0].name == "test_exp"

    def test_assignment_deterministic_across_router_instances(self) -> None:
        exp = _exp(split_percent=50)
        r1 = ExperimentRouter([exp])
        r2 = ExperimentRouter([exp])
        for req_id in [f"req-{i}" for i in range(20)]:
            p1, e1, b1 = r1.route("capable", "rule", req_id)
            p2, e2, b2 = r2.route("capable", "rule", req_id)
            assert p1 == p2
            assert b1 == b2
