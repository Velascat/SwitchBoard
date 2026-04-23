from __future__ import annotations

from pathlib import Path

from switchboard.lane.policy import LaneRoutingPolicy


def test_policy_yaml_is_canonical_lane_policy() -> None:
    policy = LaneRoutingPolicy.from_yaml(
        Path(__file__).resolve().parents[2] / "config" / "policy.yaml"
    )

    assert all(rule.select_lane for rule in policy.rules)
    assert all(rule.select_backend for rule in policy.rules)
    assert not any("profile" in rule.name for rule in policy.rules)
    assert policy.fallback.lane
    assert policy.fallback.backend

