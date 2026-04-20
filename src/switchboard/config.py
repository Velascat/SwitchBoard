"""Application configuration loaded from environment variables and .env files."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration for SwitchBoard.

    Values are read from environment variables first, then from a `.env` file
    in the current working directory.  Every variable has a sensible default so
    the service starts without any configuration for local development.

    Environment variable names use the ``SWITCHBOARD_`` prefix (or provider-
    specific prefixes) and match the names documented in ``.env.example``.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Service binding
    host: str = Field(
        default="0.0.0.0",
        alias="SWITCHBOARD_HOST",
        description="Host SwitchBoard binds to.",
    )
    port: int = Field(
        default=20401,
        alias="SWITCHBOARD_PORT",
        description="TCP port SwitchBoard listens on.",
    )

    # Observability
    log_level: str = Field(
        default="info",
        alias="SWITCHBOARD_LOG_LEVEL",
        description="Python logging level: debug, info, warning, error, critical.",
    )

    # Configuration file paths (relative to cwd or absolute)
    policy_path: str = Field(
        default="./config/policy.yaml",
        alias="SWITCHBOARD_POLICY_PATH",
        description="Path to the policy rules YAML file.",
    )
    profiles_path: str = Field(
        default="./config/profiles.yaml",
        alias="SWITCHBOARD_PROFILES_PATH",
        description="Path to the model profiles YAML file.",
    )
    capabilities_path: str = Field(
        default="./config/capabilities.yaml",
        alias="SWITCHBOARD_CAPABILITIES_PATH",
        description="Path to the capability registry YAML file.",
    )

    # Decision log
    decision_log_path: str = Field(
        default="./runtime/decisions.jsonl",
        alias="SWITCHBOARD_DECISION_LOG_PATH",
        description="Path to write decision log JSONL. Empty string disables logging.",
    )

    # Downstream 9router
    nine_router_url: str = Field(
        default="http://localhost:20128",
        alias="ROUTER9_BASE_URL",
        description="Base URL of the 9router instance.",
    )
    nine_router_chat_completions_path: str = Field(
        default="/v1/chat/completions",
        alias="ROUTER9_CHAT_COMPLETIONS_PATH",
        description="Path for chat completions on the 9router instance.",
    )
    nine_router_timeout_s: int = Field(
        default=120,
        alias="ROUTER9_TIMEOUT_S",
        description="Timeout in seconds for requests to 9router.",
    )

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"debug", "info", "warning", "error", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"log_level must be one of {allowed}, got {v!r}")
        return v.lower()

    def resolve_path(self, attr: str) -> Path:
        """Return the given config path resolved relative to cwd."""
        raw = getattr(self, attr)
        p = Path(raw)
        if not p.is_absolute():
            p = Path(os.getcwd()) / p
        return p


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    """Return the singleton Settings instance (cached after first call)."""
    return Settings()
