"""Unit tests for PolicyEngine."""

import pytest

from switchboard.domain.models import SelectionContext
from switchboard.domain.policy_types import PolicyConfig, PolicyRule
from switchboard.services.policy_engine import PolicyEngine


def _make_context(**kwargs) -> SelectionContext:
    defaults: dict = {
        "messages": [],
        "model_hint": "",
        "stream": False,
        "tools_present": False,
        "estimated_tokens": 100,
        "priority": None,
        "tenant_id": None,
        "force_profile": None,
    }
    defaults.update(kwargs)
    return SelectionContext(**defaults)


def _make_policy(*rules: PolicyRule, fallback: str = "default") -> PolicyConfig:
    return PolicyConfig(fallback_profile=fallback, rules=list(rules))


def _make_store(config: PolicyConfig):
    """Return a minimal policy_store mock."""
    class _Store:
        def get_policy(self) -> PolicyConfig:
            return config
    return _Store()


# ---------------------------------------------------------------------------
# Fallback behaviour
# ---------------------------------------------------------------------------

class TestFallback:
    def test_no_rules_uses_fallback(self) -> None:
        engine = PolicyEngine(_make_store(_make_policy(fallback="default")))
        profile, rule = engine.select_profile(_make_context())
        assert profile == "default"
        assert rule == "fallback"

    def test_no_matching_rule_uses_fallback(self) -> None:
        rule = PolicyRule(name="r1", priority=10, profile="capable",
                          conditions={"priority": "high"})
        engine = PolicyEngine(_make_store(_make_policy(rule, fallback="default")))
        ctx = _make_context(priority="low")
        profile, rule_name = engine.select_profile(ctx)
        assert profile == "default"
        assert rule_name == "fallback"


# ---------------------------------------------------------------------------
# Force profile header
# ---------------------------------------------------------------------------

class TestForceProfile:
    def test_force_profile_bypasses_all_rules(self) -> None:
        rule = PolicyRule(name="r1", priority=10, profile="capable",
                          conditions={"priority": "high"})
        engine = PolicyEngine(_make_store(_make_policy(rule, fallback="default")))
        ctx = _make_context(force_profile="local", priority="low")
        profile, rule_name = engine.select_profile(ctx)
        assert profile == "local"
        assert rule_name == "force_profile"


# ---------------------------------------------------------------------------
# Condition matching
# ---------------------------------------------------------------------------

class TestConditionMatching:
    def test_scalar_condition_matches(self) -> None:
        rule = PolicyRule(name="r1", priority=10, profile="fast",
                          conditions={"stream": True})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        profile, rule_name = engine.select_profile(_make_context(stream=True))
        assert profile == "fast"
        assert rule_name == "r1"

    def test_scalar_condition_does_not_match(self) -> None:
        rule = PolicyRule(name="r1", priority=10, profile="fast",
                          conditions={"stream": True})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        profile, _ = engine.select_profile(_make_context(stream=False))
        assert profile == "default"  # fallback

    def test_list_condition_any_of(self) -> None:
        rule = PolicyRule(name="r1", priority=10, profile="capable",
                          conditions={"model_hint": ["capable", "gpt-4o"]})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        profile, _ = engine.select_profile(_make_context(model_hint="gpt-4o"))
        assert profile == "capable"

    def test_list_condition_no_match(self) -> None:
        rule = PolicyRule(name="r1", priority=10, profile="capable",
                          conditions={"model_hint": ["capable", "gpt-4o"]})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        profile, _ = engine.select_profile(_make_context(model_hint="gpt-3.5-turbo"))
        assert profile == "default"

    def test_min_estimated_tokens(self) -> None:
        rule = PolicyRule(name="large", priority=10, profile="capable",
                          conditions={"min_estimated_tokens": 1000})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        assert engine.select_profile(_make_context(estimated_tokens=1001))[0] == "capable"
        assert engine.select_profile(_make_context(estimated_tokens=999))[0] == "default"

    def test_max_estimated_tokens(self) -> None:
        rule = PolicyRule(name="short", priority=10, profile="fast",
                          conditions={"max_estimated_tokens": 500})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        assert engine.select_profile(_make_context(estimated_tokens=499))[0] == "fast"
        assert engine.select_profile(_make_context(estimated_tokens=501))[0] == "default"

    def test_min_max_tokens(self) -> None:
        rule = PolicyRule(name="long_out", priority=10, profile="capable",
                          conditions={"min_max_tokens": 2048})
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        assert engine.select_profile(_make_context(max_tokens=4096))[0] == "capable"
        assert engine.select_profile(_make_context(max_tokens=1024))[0] == "default"
        # No max_tokens set — condition should not match
        assert engine.select_profile(_make_context(max_tokens=None))[0] == "default"

    def test_multiple_conditions_all_must_match(self) -> None:
        rule = PolicyRule(
            name="r1", priority=10, profile="fast",
            conditions={"stream": True, "max_estimated_tokens": 512},
        )
        engine = PolicyEngine(_make_store(_make_policy(rule)))
        # Both match
        assert engine.select_profile(
            _make_context(stream=True, estimated_tokens=100)
        )[0] == "fast"
        # Only stream matches
        assert engine.select_profile(
            _make_context(stream=True, estimated_tokens=1000)
        )[0] == "default"
        # Only tokens match
        assert engine.select_profile(
            _make_context(stream=False, estimated_tokens=100)
        )[0] == "default"


# ---------------------------------------------------------------------------
# Priority ordering
# ---------------------------------------------------------------------------

class TestPriorityOrdering:
    def test_lower_priority_number_wins(self) -> None:
        """Rule with priority=5 should beat priority=10 even if both match."""
        r_high = PolicyRule(name="high_prio", priority=5, profile="capable",
                            conditions={})  # always matches
        r_low = PolicyRule(name="low_prio", priority=10, profile="fast",
                           conditions={})   # also always matches
        engine = PolicyEngine(_make_store(_make_policy(r_low, r_high)))
        profile, rule_name = engine.select_profile(_make_context())
        assert profile == "capable"
        assert rule_name == "high_prio"

    def test_first_matching_rule_wins(self) -> None:
        r1 = PolicyRule(name="r1", priority=10, profile="fast",
                        conditions={"stream": True})
        r2 = PolicyRule(name="r2", priority=20, profile="capable",
                        conditions={"tools_present": True})
        engine = PolicyEngine(_make_store(_make_policy(r1, r2)))

        # Only r1 should match this context
        profile, rule_name = engine.select_profile(
            _make_context(stream=True, tools_present=False)
        )
        assert profile == "fast"
        assert rule_name == "r1"

    def test_tools_rule_takes_precedence_over_stream_rule(self) -> None:
        r_stream = PolicyRule(name="stream_rule", priority=5, profile="fast",
                              conditions={"stream": True})
        r_tools = PolicyRule(name="tool_rule", priority=3, profile="capable",
                             conditions={"tools_present": True})
        engine = PolicyEngine(_make_store(_make_policy(r_stream, r_tools)))

        # Both conditions match, but tool_rule has lower priority number → wins
        profile, rule_name = engine.select_profile(
            _make_context(stream=True, tools_present=True)
        )
        assert profile == "capable"
        assert rule_name == "tool_rule"


# ---------------------------------------------------------------------------
# Reload
# ---------------------------------------------------------------------------

class TestReload:
    def test_reload_clears_cache(self) -> None:
        config_v1 = _make_policy(
            PolicyRule(name="r1", priority=10, profile="fast", conditions={}),
            fallback="default",
        )
        config_v2 = _make_policy(
            PolicyRule(name="r2", priority=10, profile="capable", conditions={}),
            fallback="default",
        )

        call_count = [0]
        configs = [config_v1, config_v2]

        class _VersionedStore:
            def get_policy(self) -> PolicyConfig:
                cfg = configs[min(call_count[0], 1)]
                call_count[0] += 1
                return cfg

        engine = PolicyEngine(_VersionedStore())
        profile_1, _ = engine.select_profile(_make_context())
        assert profile_1 == "fast"

        engine.reload()
        profile_2, _ = engine.select_profile(_make_context())
        assert profile_2 == "capable"
