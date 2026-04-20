"""Distributed tracing stubs for SwitchBoard.

Currently a no-op shim.  The API is compatible with OpenTelemetry so that a
real OTEL tracer can be wired in without modifying call sites.

Usage::

    from switchboard.observability.tracing import get_tracer

    tracer = get_tracer(__name__)
    with tracer.start_as_current_span("policy_evaluation") as span:
        span.set_attribute("profile", "fast")
        ...
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator


class _NoOpSpan:
    """A span that does nothing."""

    def set_attribute(self, key: str, value: Any) -> None:  # noqa: ARG002
        pass

    def record_exception(self, exc: Exception) -> None:  # noqa: ARG002
        pass

    def set_status(self, status: Any) -> None:  # noqa: ARG002
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


class _NoOpTracer:
    """A tracer that produces no-op spans."""

    @contextmanager
    def start_as_current_span(
        self,
        name: str,  # noqa: ARG002
        **kwargs: Any,  # noqa: ARG002
    ) -> Generator[_NoOpSpan, None, None]:
        yield _NoOpSpan()


_tracer_cache: dict[str, _NoOpTracer] = {}


def get_tracer(name: str) -> _NoOpTracer:
    """Return a (no-op) tracer for the given instrumentation scope.

    When OpenTelemetry is integrated, replace this function with::

        from opentelemetry import trace
        def get_tracer(name: str):
            return trace.get_tracer(name)

    Args:
        name: Instrumentation scope name, typically ``__name__``.

    Returns:
        A tracer instance (currently a no-op).
    """
    if name not in _tracer_cache:
        _tracer_cache[name] = _NoOpTracer()
    return _tracer_cache[name]
