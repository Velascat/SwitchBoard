"""SwitchBoard domain layer — core models and types."""

from switchboard.domain.capability_model import CapabilityModel
from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.policy_rule import PolicyConfig, PolicyRule
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult

__all__ = [
    "CapabilityModel",
    "DecisionRecord",
    "PolicyConfig",
    "PolicyRule",
    "SelectionContext",
    "SelectionResult",
]
