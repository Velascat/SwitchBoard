"""Unit tests for ConfigValidator."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from switchboard.config.validator import ConfigValidationError, ConfigValidator
from switchboard.domain.policy_rule import ExperimentConfig, PolicyConfig, PolicyRule


def _make_settings(
    policy_path: str = "/tmp/policy.yaml",
    profiles_path: str = "/tmp/profiles.yaml",
    capabilities_path: str = "/tmp/capabilities.yaml",
) -> MagicMock:
    settings = MagicMock()
    settings.resolve_path.side_effect = lambda attr: Path(
        {
            "policy_path": policy_path,
            "profiles_path": profiles_path,
            "capabilities_path": capabilities_path,
        }[attr]
    )
    return settings


def _make_policy(
    rules: list | None = None,
    fallback_profile: str = "default",
    experiments: list | None = None,
) -> PolicyConfig:
    return PolicyConfig(
        fallback_profile=fallback_profile,
        rules=rules or [],
        experiments=experiments or [],
    )


def _make_rule(name: str, profile: str = "fast") -> PolicyRule:
    return PolicyRule(name=name, select_profile=profile, when={})


def _make_stores(
    policy: PolicyConfig | None = None,
    profiles: dict | None = None,
    capabilities: dict | None = None,
) -> tuple:
    policy_store = MagicMock()
    policy_store.get_policy.return_value = policy or _make_policy()

    profile_store = MagicMock()
    profile_store.get_profiles.return_value = profiles or {"fast": {}, "capable": {}, "default": {}}

    capability_registry = MagicMock()
    capability_registry.all_profiles.return_value = capabilities or {
        "fast": {},
        "capable": {},
        "default": {},
    }

    return policy_store, profile_store, capability_registry


def _existing(tmp_path: Path) -> Path:
    p = tmp_path / "file.yaml"
    p.write_text("version: 1")
    return p


# ---------------------------------------------------------------------------
# File existence
# ---------------------------------------------------------------------------


class TestFileExistence:
    def test_passes_when_all_files_exist(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        policy_store, profile_store, cap_reg = _make_stores()
        ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)  # no raise

    def test_fails_when_policy_missing(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(
            policy_path="/nonexistent/policy.yaml",
            profiles_path=path,
            capabilities_path=path,
        )
        policy_store, profile_store, cap_reg = _make_stores()
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "Policy" in str(exc_info.value)

    def test_fails_when_profiles_missing(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(
            policy_path=path,
            profiles_path="/nonexistent/profiles.yaml",
            capabilities_path=path,
        )
        policy_store, profile_store, cap_reg = _make_stores()
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "Profiles" in str(exc_info.value)

    def test_fails_when_capabilities_missing(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(
            policy_path=path,
            profiles_path=path,
            capabilities_path="/nonexistent/cap.yaml",
        )
        policy_store, profile_store, cap_reg = _make_stores()
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "Capabilities" in str(exc_info.value)

    def test_error_message_lists_all_missing_files(self, tmp_path: Path) -> None:
        settings = _make_settings(
            policy_path="/nope/policy.yaml",
            profiles_path="/nope/profiles.yaml",
            capabilities_path="/nope/cap.yaml",
        )
        policy_store, profile_store, cap_reg = _make_stores()
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert len(exc_info.value.errors) == 3


# ---------------------------------------------------------------------------
# Policy load failure
# ---------------------------------------------------------------------------


class TestPolicyLoadFailure:
    def test_fails_when_policy_store_raises(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        policy_store = MagicMock()
        policy_store.get_policy.side_effect = ValueError("bad YAML")
        _, profile_store, cap_reg = _make_stores()
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "could not be loaded" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Duplicate rule names
# ---------------------------------------------------------------------------


class TestDuplicateRuleNames:
    def test_fails_on_duplicate_rule_names(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        policy = _make_policy(rules=[_make_rule("same_name"), _make_rule("same_name")])
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "Duplicate" in str(exc_info.value)
        assert "same_name" in str(exc_info.value)

    def test_passes_unique_rule_names(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        policy = _make_policy(rules=[_make_rule("rule_a"), _make_rule("rule_b")])
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)  # no raise


# ---------------------------------------------------------------------------
# Experiment validation
# ---------------------------------------------------------------------------


class TestExperimentValidation:
    def test_fails_when_split_percent_out_of_range(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        exp = ExperimentConfig(name="bad", profile_a="capable", profile_b="fast", split_percent=101)
        policy = _make_policy(experiments=[exp])
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "split_percent" in str(exc_info.value)

    def test_fails_when_profile_a_equals_profile_b(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        exp = ExperimentConfig(name="same", profile_a="fast", profile_b="fast", split_percent=10)
        policy = _make_policy(experiments=[exp])
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        with pytest.raises(ConfigValidationError) as exc_info:
            ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)
        assert "must be different" in str(exc_info.value)

    def test_valid_experiment_passes(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        exp = ExperimentConfig(name="ok", profile_a="capable", profile_b="fast", split_percent=10)
        policy = _make_policy(experiments=[exp])
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)


# ---------------------------------------------------------------------------
# Warnings (non-critical)
# ---------------------------------------------------------------------------


class TestValidatorWarnings:
    def test_warns_but_does_not_raise_for_unknown_rule_profile(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        # Rule references "unknown_profile" which isn't in capability registry
        policy = _make_policy(rules=[_make_rule("rule1", profile="unknown_profile")])
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        # Should NOT raise
        ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)

    def test_warns_but_does_not_raise_for_unknown_fallback(self, tmp_path: Path) -> None:
        path = str(_existing(tmp_path))
        settings = _make_settings(policy_path=path, profiles_path=path, capabilities_path=path)
        policy = _make_policy(fallback_profile="nonexistent")
        policy_store, profile_store, cap_reg = _make_stores(policy=policy)
        ConfigValidator().validate_all(settings, policy_store, profile_store, cap_reg)


# ---------------------------------------------------------------------------
# ConfigValidationError
# ---------------------------------------------------------------------------


class TestConfigValidationError:
    def test_error_list_accessible(self) -> None:
        err = ConfigValidationError(["error one", "error two"])
        assert len(err.errors) == 2

    def test_str_includes_all_errors(self) -> None:
        err = ConfigValidationError(["first error", "second error"])
        msg = str(err)
        assert "first error" in msg
        assert "second error" in msg

    def test_error_count_in_message(self) -> None:
        err = ConfigValidationError(["e1", "e2", "e3"])
        assert "3" in str(err)
