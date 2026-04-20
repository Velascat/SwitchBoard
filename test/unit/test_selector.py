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
