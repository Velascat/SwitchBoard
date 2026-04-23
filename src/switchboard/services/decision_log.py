"""Re-export shim for canonical decision logging."""

from switchboard.services.decision_logger import DecisionLogger

# Alias so existing code that does ``from services.decision_log import DecisionLog``
# still works.
DecisionLog = DecisionLogger

__all__ = ["DecisionLog", "DecisionLogger"]
