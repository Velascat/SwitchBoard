"""Unit tests for ProfileRegistry."""

from unittest.mock import MagicMock

import pytest

from switchboard.services.profile_registry import ProfileRegistry

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_profile_store(profiles: dict) -> MagicMock:
    """Return a minimal profile_store mock that returns ``profiles``."""
    store = MagicMock()
    store.get_profiles.return_value = profiles
    return store


def _make_registry(profiles: dict) -> ProfileRegistry:
    return ProfileRegistry(_make_profile_store(profiles))


# ---------------------------------------------------------------------------
# Load profiles
# ---------------------------------------------------------------------------


class TestLoadProfiles:
    def test_get_profiles_returns_all(self) -> None:
        profiles = {
            "fast": {"downstream_model": "gpt-4o-mini", "tags": ["chat"]},
            "capable": {"downstream_model": "gpt-4o", "tags": ["reasoning"]},
        }
        registry = _make_registry(profiles)
        result = registry.get_profiles()
        assert set(result.keys()) == {"fast", "capable"}

    def test_get_profiles_empty(self) -> None:
        registry = _make_registry({})
        assert registry.get_profiles() == {}

    def test_all_profile_names_sorted(self) -> None:
        profiles = {
            "capable": {"downstream_model": "gpt-4o"},
            "fast": {"downstream_model": "gpt-4o-mini"},
            "local": {"downstream_model": "llama3"},
        }
        registry = _make_registry(profiles)
        assert registry.all_profile_names() == ["capable", "fast", "local"]


# ---------------------------------------------------------------------------
# Resolve profile → downstream model
# ---------------------------------------------------------------------------


class TestResolveProfile:
    def test_resolves_known_profile(self) -> None:
        profiles = {
            "fast": {"downstream_model": "gpt-4o-mini"},
            "capable": {"downstream_model": "gpt-4o"},
        }
        registry = _make_registry(profiles)
        assert registry.resolve_profile("fast") == "gpt-4o-mini"
        assert registry.resolve_profile("capable") == "gpt-4o"

    def test_raises_key_error_for_missing_profile(self) -> None:
        registry = _make_registry({"fast": {"downstream_model": "gpt-4o-mini"}})
        with pytest.raises(KeyError, match="ghost"):
            registry.resolve_profile("ghost")

    def test_raises_value_error_when_no_downstream_model(self) -> None:
        registry = _make_registry({"broken": {}})
        with pytest.raises(ValueError, match="downstream_model"):
            registry.resolve_profile("broken")

    def test_raises_value_error_when_downstream_model_empty(self) -> None:
        registry = _make_registry({"empty": {"downstream_model": ""}})
        with pytest.raises(ValueError, match="downstream_model"):
            registry.resolve_profile("empty")


# ---------------------------------------------------------------------------
# profile_exists
# ---------------------------------------------------------------------------


class TestProfileExists:
    def test_returns_true_for_known_profile(self) -> None:
        registry = _make_registry({"fast": {"downstream_model": "gpt-4o-mini"}})
        assert registry.profile_exists("fast") is True

    def test_returns_false_for_unknown_profile(self) -> None:
        registry = _make_registry({"fast": {"downstream_model": "gpt-4o-mini"}})
        assert registry.profile_exists("ghost") is False
