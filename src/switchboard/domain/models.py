"""Re-export shim for core domain models.

All domain models have been split into dedicated modules.  This shim re-exports
them from their canonical locations so that existing import paths continue to
work without modification.
"""

from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult

__all__ = [
    "DecisionRecord",
    "SelectionContext",
    "SelectionResult",
]
