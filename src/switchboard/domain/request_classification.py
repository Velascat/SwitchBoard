"""RequestClassifier — thin domain wrapper re-exported for backwards compat.

The full implementation lives in :mod:`switchboard.services.classifier`.
This module re-exports :class:`RequestClassifier` so that domain-layer imports
remain stable regardless of where the implementation moves.
"""

from switchboard.services.classifier import RequestClassifier

__all__ = ["RequestClassifier"]
