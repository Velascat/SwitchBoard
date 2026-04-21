"""ConfigValidator — validates the full configuration at startup.

Validates all configuration sources before the service starts accepting traffic.
Critical errors raise :class:`ConfigValidationError` so the service fails fast
with a clear diagnostic.  Non-critical issues are logged as warnings.

Validation checks
-----------------
Critical (raise on failure):
    1.  Policy / profiles / capabilities files exist on disk.
    2.  All three YAML files parse without error.
    3.  No duplicate rule names in policy.
    4.  Experiment ``split_percent`` values are in the range 0–100.
    5.  Experiments have distinct ``profile_a`` and ``profile_b``.

Warnings (logged, service continues):
    W1. Profiles referenced by rules are not in the capability registry.
    W2. The policy fallback profile is not in the capability registry.
    W3. Profiles referenced by experiments are not in the capability registry.
"""

from __future__ import annotations

from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class ConfigValidationError(Exception):
    """Raised when one or more critical configuration errors are found."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        bullet = "\n".join(f"  • {e}" for e in errors)
        super().__init__(f"Configuration validation failed ({len(errors)} error(s)):\n{bullet}")


class ConfigValidator:
    """Validates SwitchBoard configuration at startup."""

    def validate_all(
        self,
        settings,
        policy_store,
        profile_store,
        capability_registry,
    ) -> None:
        """Run all validation checks.

        Args:
            settings:            Loaded :class:`~switchboard.config.Settings` instance.
            policy_store:        Loaded :class:`FilePolicyStore`.
            profile_store:       Loaded :class:`FileProfileStore`.
            capability_registry: Loaded :class:`CapabilityRegistry`.

        Raises:
            ConfigValidationError: If any critical validation checks fail.
        """
        errors: list[str] = []
        warnings: list[str] = []

        # ------------------------------------------------------------------
        # 1. File existence
        # ------------------------------------------------------------------
        for attr, label in [
            ("policy_path", "Policy"),
            ("profiles_path", "Profiles"),
            ("capabilities_path", "Capabilities"),
        ]:
            path = settings.resolve_path(attr)
            if not path.exists():
                errors.append(f"{label} file not found: {path}")

        if errors:
            raise ConfigValidationError(errors)

        # ------------------------------------------------------------------
        # 2. Load configs — surface parse errors early
        # ------------------------------------------------------------------
        try:
            policy = policy_store.get_policy()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Policy file could not be loaded: {exc}")
            raise ConfigValidationError(errors) from exc

        try:
            profile_store.get_profiles()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Profiles file could not be loaded: {exc}")

        try:
            capabilities = capability_registry.all_profiles()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Capabilities file could not be loaded: {exc}")
            capabilities = {}

        if errors:
            raise ConfigValidationError(errors)

        # ------------------------------------------------------------------
        # 3. Duplicate rule names
        # ------------------------------------------------------------------
        seen_names: set[str] = set()
        for rule in policy.rules:
            if rule.name in seen_names:
                errors.append(f"Duplicate policy rule name: {rule.name!r}")
            seen_names.add(rule.name)

        # ------------------------------------------------------------------
        # 4. Experiment bounds and distinctness
        # ------------------------------------------------------------------
        for exp in policy.experiments:
            if not (0 <= exp.split_percent <= 100):
                errors.append(
                    f"Experiment {exp.name!r}: split_percent must be 0–100, "
                    f"got {exp.split_percent}"
                )
            if exp.profile_a == exp.profile_b:
                errors.append(
                    f"Experiment {exp.name!r}: profile_a and profile_b must be different"
                )

        if errors:
            raise ConfigValidationError(errors)

        # ------------------------------------------------------------------
        # 5. Soft checks — warn but do not fail
        # ------------------------------------------------------------------
        for rule in policy.rules:
            p = rule.resolved_profile
            if p and p not in capabilities:
                warnings.append(
                    f"Rule {rule.name!r} references profile {p!r} "
                    f"which is not in the capability registry"
                )

        if policy.fallback_profile and policy.fallback_profile not in capabilities:
            warnings.append(
                f"Fallback profile {policy.fallback_profile!r} is not in the capability registry"
            )

        for exp in policy.experiments:
            for profile_attr, p in [("profile_a", exp.profile_a), ("profile_b", exp.profile_b)]:
                if p and p not in capabilities:
                    warnings.append(
                        f"Experiment {exp.name!r}: {profile_attr}={p!r} "
                        f"is not in the capability registry"
                    )

        for warning in warnings:
            logger.warning("Config warning: %s", warning)

        if warnings:
            logger.info(
                "Configuration loaded with %d warning(s) — service will start",
                len(warnings),
            )
        else:
            logger.info("Configuration validated successfully (no warnings)")
