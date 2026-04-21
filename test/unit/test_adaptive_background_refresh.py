"""Unit tests for the adaptive background refresh loop."""

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import MagicMock, patch

from switchboard.app import _adaptive_refresh_loop
from switchboard.services.adjustment_store import AdjustmentStore


def _make_store(window_size: int = 50) -> AdjustmentStore:
    store = AdjustmentStore(window_size=window_size)
    return store


def _make_logger(records=None):
    logger = MagicMock()
    logger.last_n.return_value = records or []
    return logger


async def test_loop_calls_maybe_refresh_after_sleep():
    """Loop should call maybe_refresh with the right records after each sleep."""
    store = _make_store(window_size=50)
    decision_log = _make_logger(records=["r1", "r2"])

    call_count = 0
    original = store.maybe_refresh

    def counting_refresh(records):
        nonlocal call_count
        call_count += 1
        original(records)

    store.maybe_refresh = counting_refresh

    with patch("switchboard.app._ADAPTIVE_POLL_INTERVAL_S", 0.01):
        task = asyncio.create_task(_adaptive_refresh_loop(store, decision_log))
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count >= 1
    decision_log.last_n.assert_called_with(50)


async def test_loop_stops_on_cancel():
    """Loop exits cleanly when the task is cancelled."""
    store = _make_store()
    decision_log = _make_logger()

    with patch("switchboard.app._ADAPTIVE_POLL_INTERVAL_S", 0.01):
        task = asyncio.create_task(_adaptive_refresh_loop(store, decision_log))
        await asyncio.sleep(0.02)
        task.cancel()
        await task  # should not raise after CancelledError is caught


async def test_loop_continues_after_exception():
    """Exceptions from maybe_refresh are caught; the loop keeps running."""
    store = _make_store()
    decision_log = _make_logger()

    call_count = 0

    def flaky_refresh(records):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("transient error")

    store.maybe_refresh = flaky_refresh

    with patch("switchboard.app._ADAPTIVE_POLL_INTERVAL_S", 0.01):
        task = asyncio.create_task(_adaptive_refresh_loop(store, decision_log))
        await asyncio.sleep(0.05)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert call_count >= 2


def test_adjustment_store_window_size_property():
    store = AdjustmentStore(window_size=123)
    assert store.window_size == 123
