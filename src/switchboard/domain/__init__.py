# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""SwitchBoard domain layer — core models and types."""

from switchboard.domain.capability_model import CapabilityModel
from switchboard.domain.decision_record import DecisionRecord

__all__ = [
    "CapabilityModel",
    "DecisionRecord",
]
