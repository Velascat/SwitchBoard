"""Re-export shim for SelectionResult and DecisionRecord.

:class:`SelectionResult` and :class:`DecisionRecord` are defined in
:mod:`switchboard.domain.models` (sections 8.2 and 8.3).  This module
re-exports them for consumers that import from this path specifically.
"""

from switchboard.domain.models import DecisionRecord, SelectionResult

__all__ = ["DecisionRecord", "SelectionResult"]
