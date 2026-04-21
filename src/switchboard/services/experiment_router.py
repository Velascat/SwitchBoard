"""ExperimentRouter — controlled A/B routing for profile experiments.

Routes a deterministic percentage of traffic to an alternative profile
(the "treatment") while the remainder continues to the original profile
(the "control").  Assignment is determined by hashing the request ID and
experiment name — the same request always falls in the same bucket.

This means:
  - Reproducible: re-running a request gets the same treatment.
  - Observable: ``ab_experiment`` and ``ab_bucket`` appear in every decision record.
  - Safe: ``force_profile`` rules are never intercepted.
"""

from __future__ import annotations

import hashlib

from switchboard.domain.policy_rule import ExperimentConfig
from switchboard.observability.logging import get_logger

logger = get_logger(__name__)


class ExperimentRouter:
    """Applies active A/B experiments to a (profile, rule_name) decision."""

    def __init__(self, experiments: list[ExperimentConfig]) -> None:
        self._experiments = [e for e in experiments if e.enabled]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        profile: str,
        rule_name: str,
        request_id: str,
    ) -> tuple[str, str | None, str | None]:
        """Apply any matching experiment to the given profile selection.

        Args:
            profile:     The profile selected by the policy engine.
            rule_name:   The rule that produced the selection (force_profile is skipped).
            request_id:  Correlation ID used for deterministic bucket assignment.

        Returns:
            ``(final_profile, experiment_name | None, bucket | None)``
            where ``bucket`` is ``"A"`` (control) or ``"B"`` (treatment).
        """
        if rule_name == "force_profile":
            return profile, None, None

        for experiment in self._experiments:
            if experiment.profile_a != profile:
                continue
            if experiment.applies_to_rules and rule_name not in experiment.applies_to_rules:
                continue

            bucket = _assign_bucket(request_id, experiment.name, experiment.split_percent)
            if bucket == "B":
                logger.info(
                    "A/B experiment=%r: request_id=%r assigned to bucket=B → profile=%r",
                    experiment.name,
                    request_id,
                    experiment.profile_b,
                )
                return experiment.profile_b, experiment.name, "B"
            else:
                logger.debug(
                    "A/B experiment=%r: request_id=%r assigned to bucket=A (control)",
                    experiment.name,
                    request_id,
                )
                return profile, experiment.name, "A"

        return profile, None, None

    @property
    def active_experiments(self) -> list[ExperimentConfig]:
        return list(self._experiments)


# ---------------------------------------------------------------------------
# Deterministic bucket assignment
# ---------------------------------------------------------------------------

def _assign_bucket(request_id: str, experiment_name: str, split_percent: int) -> str:
    """Deterministically assign a request to bucket A or B.

    Uses SHA-256 of ``(request_id + ":" + experiment_name)`` to produce a
    stable 0–99 integer.  Values < ``split_percent`` are bucket B (treatment).
    """
    raw = f"{request_id}:{experiment_name}".encode()
    digest = hashlib.sha256(raw).digest()
    # Use the first 4 bytes as a uint32 and take mod 100
    value = int.from_bytes(digest[:4], "big") % 100
    return "B" if value < split_percent else "A"
