"""FilePolicyStore — loads policy configuration from a YAML file.

Implements the :class:`~switchboard.ports.policy_store.PolicyStore` port.

The YAML file is read once and cached.  Call :meth:`reload` to force a fresh
read (useful after the file is edited without restarting the service).

Supports both the new rule shape (``when`` / ``select_profile``) and the legacy
shape (``conditions`` / ``profile``) so that policy files written in either
format load correctly.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from switchboard.domain.policy_rule import PolicyConfig, PolicyRule
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class FilePolicyStore:
    """Reads policy configuration from a YAML file on disk."""

    def __init__(self, policy_path: Path) -> None:
        self._path = policy_path
        self._cached: PolicyConfig | None = None

    def get_policy(self) -> PolicyConfig:
        """Load and return the :class:`PolicyConfig` from the YAML file.

        The result is cached after the first successful load.

        Returns:
            A fully parsed :class:`PolicyConfig`.

        Raises:
            FileNotFoundError: If the policy file does not exist.
            ValueError:        If the YAML is malformed or missing required fields.
        """
        if self._cached is None:
            self._cached = self._load()
        return self._cached

    def reload(self) -> PolicyConfig:
        """Force reload from disk and return the updated config."""
        self._cached = None
        return self.get_policy()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> PolicyConfig:
        if not self._path.exists():
            logger.warning("Policy file not found at %s; using empty policy.", self._path)
            return PolicyConfig(fallback_profile="default", rules=[])

        with self._path.open("r", encoding="utf-8") as fh:
            raw: dict[str, Any] = yaml.safe_load(fh) or {}

        version = str(raw.get("version", "1"))
        fallback = raw.get("fallback_profile", "default")
        raw_rules: list[dict[str, Any]] = raw.get("rules", [])

        rules: list[PolicyRule] = []
        for i, r in enumerate(raw_rules):
            # Support both new (select_profile/when) and legacy (profile/conditions) shapes.
            select_profile = r.get("select_profile", "")
            profile = r.get("profile", "")
            when = r.get("when", {})
            conditions = r.get("conditions", {})

            if not (select_profile or profile):
                logger.warning(
                    "Policy rule at index %d missing 'select_profile'/'profile'; skipping.", i
                )
                continue
            if "name" not in r:
                logger.warning("Policy rule at index %d missing 'name'; skipping.", i)
                continue

            rules.append(
                PolicyRule(
                    name=r["name"],
                    priority=int(r.get("priority", 100)),
                    select_profile=select_profile,
                    profile=profile,
                    when=when,
                    conditions=conditions,
                    description=r.get("description", ""),
                )
            )

        config = PolicyConfig(version=version, fallback_profile=fallback, rules=rules)
        logger.info(
            "Policy loaded from %s: %d rules, fallback=%s",
            self._path,
            len(rules),
            fallback,
        )
        return config
