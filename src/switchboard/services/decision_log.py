"""Re-export shim — DecisionLog has moved to decision_logger.py.

:class:`DecisionLog` is now an alias for :class:`DecisionLogger`.  This shim
keeps existing import paths (e.g. in ``app.py`` and ``forwarder.py``) working
without modification until callers are updated.
"""

from switchboard.services.decision_logger import DecisionLogger, make_decision_record

# Alias so existing code that does ``from services.decision_log import DecisionLog``
# still works.
DecisionLog = DecisionLogger

__all__ = ["DecisionLog", "DecisionLogger", "make_decision_record"]
