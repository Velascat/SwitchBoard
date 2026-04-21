"""Unit tests for Selector."""

from unittest.mock import MagicMock

import pytest

from switchboard.domain.selection_context import SelectionContext
from switchboard.services.selector import Selector


def _make_context(**kwargs) -> SelectionContext:
    defaults = {
        "messages": [{"role": "user", "content": "hello"}],
        "model_hint": "",
        "stream": False,
        "tools_present": False,
        "estimated_tokens": 10,
    }
    defaults.update(kwargs)
    return SelectionContext(**defaults)


def _make_selector(profile_name: str, rule_name: str, downstream_model: str) -> Selector:
    """Build a Selector with mocked PolicyEngine and CapabilityRegistry."""
    policy_engine = MagicMock()
    policy_engine.select_profile.return_value = (profile_name, rule_name)

    capability_registry = MagicMock()
    capability_registry.resolve_profile.return_value = downstream_model

    return Selector(policy_engine, capability_registry)


class TestSelectorBasic:
    def test_returns_correct_profile_and_model(self) -> None:
        selector = _make_selector("capable", "high_priority_tenant", "gpt-4o")
        ctx = _make_context(priority="high")
        result = selector.select(ctx)

        assert result.profile_name == "capable"
        assert result.downstream_model == "gpt-4o"
        assert result.rule_name == "high_priority_tenant"

    def test_context_is_preserved_in_result(self) -> None:
        selector = _make_selector("fast", "default_short_request", "gpt-4o-mini")
        ctx = _make_context(model_hint="fast", estimated_tokens=50)
        result = selector.select(ctx)

        assert result.context is ctx

    def test_fallback_rule_passthrough(self) -> None:
        selector = _make_selector("default", "fallback", "gpt-4o-mini")
        ctx = _make_context()
        result = selector.select(ctx)

        assert result.rule_name == "fallback"
        assert result.profile_name == "default"

    def test_selector_calls_policy_engine_with_context(self) -> None:
        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("fast", "some_rule")
        capability_registry = MagicMock()
        capability_registry.resolve_profile.return_value = "gpt-4o-mini"

        selector = Selector(policy_engine, capability_registry)
        ctx = _make_context()
        selector.select(ctx)

        policy_engine.select_profile.assert_called_once_with(ctx)

    def test_selector_calls_registry_with_profile_name(self) -> None:
        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("capable", "tool_use")
        capability_registry = MagicMock()
        capability_registry.resolve_profile.return_value = "gpt-4o"

        selector = Selector(policy_engine, capability_registry)
        ctx = _make_context(tools_present=True)
        selector.select(ctx)

        capability_registry.resolve_profile.assert_called_once_with("capable")


class TestSelectorPassthrough:
    def test_unknown_profile_falls_back_to_model_hint(self) -> None:
        """If capability registry raises KeyError, use the model_hint as passthrough."""
        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("nonexistent_profile", "some_rule")
        capability_registry = MagicMock()
        capability_registry.resolve_profile.side_effect = KeyError("nonexistent_profile")

        selector = Selector(policy_engine, capability_registry)
        ctx = _make_context(model_hint="claude-3-5-sonnet")
        result = selector.select(ctx)

        assert result.downstream_model == "claude-3-5-sonnet"
        assert result.rule_name == "passthrough_fallback"
        assert result.profile_name == "passthrough"

    def test_unknown_profile_no_hint_raises(self) -> None:
        """If no hint and registry raises KeyError, propagate the error."""
        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("ghost_profile", "some_rule")
        capability_registry = MagicMock()
        capability_registry.resolve_profile.side_effect = KeyError("ghost_profile")

        selector = Selector(policy_engine, capability_registry)
        ctx = _make_context(model_hint="")

        with pytest.raises(KeyError):
            selector.select(ctx)


class TestSelectorForceProfile:
    def test_force_profile_header_bypasses_rules(self) -> None:
        """A force_profile in the context should still go through policy engine
        (which short-circuits internally) but context is passed correctly."""
        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("local", "force_profile")
        capability_registry = MagicMock()
        capability_registry.resolve_profile.return_value = "llama3"

        selector = Selector(policy_engine, capability_registry)
        ctx = _make_context(force_profile="local")
        result = selector.select(ctx)

        assert result.profile_name == "local"
        assert result.downstream_model == "llama3"
        assert result.rule_name == "force_profile"


# ---------------------------------------------------------------------------
# Phase 3 — eligibility validation
# ---------------------------------------------------------------------------


def _make_profile_store(profiles: dict):
    class _Store:
        def get_profiles(self):
            return profiles
    return _Store()


_PROFILES_WITH_CAPABILITIES = {
    "fast": {
        "downstream_model": "gpt-4o-mini",
        "supports_tools": True,
        "max_context_tokens": 128_000,
    },
    "capable": {
        "downstream_model": "gpt-4o",
        "supports_tools": True,
        "max_context_tokens": 128_000,
    },
    "local": {
        "downstream_model": "llama3",
        "supports_tools": False,
        "max_context_tokens": 8_192,
    },
    "default": {
        "downstream_model": "gpt-4o-mini",
        "supports_tools": True,
        "max_context_tokens": 128_000,
    },
}


def _make_selector_with_eligibility(
    policy_profile: str,
    policy_rule: str,
    profiles: dict | None = None,
) -> Selector:
    policy_engine = MagicMock()
    policy_engine.select_profile.return_value = (policy_profile, policy_rule)

    capability_registry = MagicMock()
    capability_registry.resolve_profile.side_effect = lambda name: {
        "fast": "gpt-4o-mini",
        "capable": "gpt-4o",
        "local": "llama3",
        "default": "gpt-4o-mini",
    }.get(name, "gpt-4o-mini")

    profile_store = _make_profile_store(profiles or _PROFILES_WITH_CAPABILITIES)
    return Selector(policy_engine, capability_registry, profile_store)


class TestEligibilityValidation:
    def test_tools_required_rejects_local_profile(self) -> None:
        selector = _make_selector_with_eligibility("local", "low_priority_local")
        ctx = _make_context(requires_tools=True, tools_present=True)
        result = selector.select(ctx)

        assert result.profile_name != "local"
        assert len(result.rejected_profiles) >= 1
        assert result.rejected_profiles[0]["profile"] == "local"
        assert "tool" in result.rejected_profiles[0]["reason"]

    def test_tools_required_escalates_to_capable(self) -> None:
        selector = _make_selector_with_eligibility("local", "low_priority_local")
        ctx = _make_context(requires_tools=True, tools_present=True)
        result = selector.select(ctx)

        assert result.profile_name == "capable"
        assert result.rule_name == "eligibility_fallback"

    def test_long_context_rejects_local_small_window(self) -> None:
        selector = _make_selector_with_eligibility("local", "some_rule")
        ctx = _make_context(requires_long_context=True)
        result = selector.select(ctx)

        assert result.profile_name != "local"
        assert any(r["profile"] == "local" for r in result.rejected_profiles)

    def test_eligible_profile_has_no_rejections(self) -> None:
        selector = _make_selector_with_eligibility("capable", "coding_task")
        ctx = _make_context(requires_tools=True)
        result = selector.select(ctx)

        assert result.profile_name == "capable"
        assert result.rejected_profiles == []

    def test_force_profile_skips_eligibility(self) -> None:
        selector = _make_selector_with_eligibility("local", "force_profile")
        ctx = _make_context(requires_tools=True, force_profile="local")
        result = selector.select(ctx)

        # force_profile bypasses eligibility — no rejections recorded
        assert result.profile_name == "local"
        assert result.rejected_profiles == []

    def test_reason_includes_rule_and_profile(self) -> None:
        selector = _make_selector_with_eligibility("capable", "coding_task")
        ctx = _make_context()
        result = selector.select(ctx)

        assert "capable" in result.reason
        assert "coding_task" in result.reason

    def test_reason_includes_rejection_when_rejected(self) -> None:
        selector = _make_selector_with_eligibility("local", "low_priority_local")
        ctx = _make_context(requires_tools=True, tools_present=True)
        result = selector.select(ctx)

        assert "rejected" in result.reason
        assert "local" in result.reason

    def test_no_profile_store_skips_eligibility(self) -> None:
        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("local", "some_rule")
        capability_registry = MagicMock()
        capability_registry.resolve_profile.return_value = "llama3"

        selector = Selector(policy_engine, capability_registry)  # no profile_store
        ctx = _make_context(requires_tools=True)
        result = selector.select(ctx)

        # Without profile_store, no eligibility check, no rejections
        assert result.profile_name == "local"
        assert result.rejected_profiles == []
