"""Logging configuration for SwitchBoard.

Provides:
    configure_logging(level)  — Called once at startup.
    get_logger(name)          — Returns a named logger (module-level usage).

Log format is JSON-friendly when ``LOG_LEVEL`` is ``info`` or above; verbose
format (with source location) is used for ``debug``.
"""

from __future__ import annotations

import logging
import sys

_VERBOSE_FORMAT = (
    "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d — %(message)s"
)
_STANDARD_FORMAT = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"

_configured = False


def configure_logging(level: str = "info") -> None:
    """Configure the root logger for SwitchBoard.

    Safe to call multiple times — subsequent calls are no-ops once the root
    logger has been configured.

    Args:
        level: Logging level string: ``"debug"``, ``"info"``, ``"warning"``,
               ``"error"``, or ``"critical"``.
    """
    global _configured
    if _configured:
        return

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    fmt = _VERBOSE_FORMAT if numeric_level <= logging.DEBUG else _STANDARD_FORMAT

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Avoid duplicate handlers if uvicorn has already added one.
    if not root.handlers:
        root.addHandler(handler)
    else:
        root.handlers[0].setFormatter(logging.Formatter(fmt))
        root.setLevel(numeric_level)

    # Quieten noisy third-party loggers at INFO level unless debugging.
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(
            logging.DEBUG if numeric_level <= logging.DEBUG else logging.WARNING
        )

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger.

    Usage::

        from switchboard.observability.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Hello from %s", __name__)

    Args:
        name: Logger name, typically ``__name__``.

    Returns:
        A :class:`logging.Logger` instance.
    """
    return logging.getLogger(name)
