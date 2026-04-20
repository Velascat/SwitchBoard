"""Unit tests for CapabilityRegistry."""

from pathlib import Path

import pytest
import yaml

from switchboard.services.capability_registry import CapabilityRegistry


@pytest.fixture()
def capabilities_file(tmp_path: Path) -> Path:
    data = {
        "version": "1",
        "profiles": {
            "fast": {
                "downstream_model": "gpt-4o-mini",
                "provider_hint": "openai",
            },
            "capable": {
                "downstream_model": "gpt-4o",
                "provider_hint": "openai",
            },
            "local": {
                "downstream_model": "llama3",
                "provider_hint": "ollama",
            },
        },
    }
    p = tmp_path / "capabilities.yaml"
    p.write_text(yaml.dump(data), encoding="utf-8")
    return p


class TestResolveProfile:
    def test_resolves_known_profile(self, capabilities_file: Path) -> None:
        registry = CapabilityRegistry(capabilities_file)
        assert registry.resolve_profile("fast") == "gpt-4o-mini"
        assert registry.resolve_profile("capable") == "gpt-4o"
        assert registry.resolve_profile("local") == "llama3"

    def test_raises_key_error_for_unknown_profile(self, capabilities_file: Path) -> None:
        registry = CapabilityRegistry(capabilities_file)
        with pytest.raises(KeyError, match="ghost"):
            registry.resolve_profile("ghost")

    def test_provider_hint_returned(self, capabilities_file: Path) -> None:
        registry = CapabilityRegistry(capabilities_file)
        assert registry.get_provider_hint("fast") == "openai"
        assert registry.get_provider_hint("local") == "ollama"

    def test_provider_hint_none_for_unknown(self, capabilities_file: Path) -> None:
        registry = CapabilityRegistry(capabilities_file)
        assert registry.get_provider_hint("nonexistent") is None

    def test_all_profiles_returns_all(self, capabilities_file: Path) -> None:
        registry = CapabilityRegistry(capabilities_file)
        profiles = registry.all_profiles()
        assert set(profiles.keys()) == {"fast", "capable", "local"}


class TestMissingFile:
    def test_missing_file_returns_empty_registry(self, tmp_path: Path) -> None:
        registry = CapabilityRegistry(tmp_path / "missing.yaml")
        profiles = registry.all_profiles()
        assert profiles == {}

    def test_missing_file_raises_key_error_on_resolve(self, tmp_path: Path) -> None:
        registry = CapabilityRegistry(tmp_path / "missing.yaml")
        with pytest.raises(KeyError):
            registry.resolve_profile("fast")


class TestReload:
    def test_reload_picks_up_file_changes(self, tmp_path: Path) -> None:
        p = tmp_path / "caps.yaml"
        p.write_text(
            yaml.dump({"version": "1", "profiles": {"fast": {"downstream_model": "old-model"}}}),
            encoding="utf-8",
        )
        registry = CapabilityRegistry(p)
        assert registry.resolve_profile("fast") == "old-model"

        # Update file on disk
        p.write_text(
            yaml.dump({"version": "1", "profiles": {"fast": {"downstream_model": "new-model"}}}),
            encoding="utf-8",
        )
        registry.reload()
        assert registry.resolve_profile("fast") == "new-model"


class TestCaching:
    def test_file_read_only_once(self, capabilities_file: Path, monkeypatch) -> None:
        read_count = [0]
        original_open = Path.open

        def counting_open(self, *args, **kwargs):
            if self == capabilities_file:
                read_count[0] += 1
            return original_open(self, *args, **kwargs)

        monkeypatch.setattr(Path, "open", counting_open)
        registry = CapabilityRegistry(capabilities_file)

        registry.resolve_profile("fast")
        registry.resolve_profile("capable")
        registry.resolve_profile("local")

        assert read_count[0] == 1, "File should only be read once due to caching"
