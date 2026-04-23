"""Unit tests for AdjustmentStore."""

from __future__ import annotations

from unittest.mock import MagicMock

from switchboard.domain.decision_record import DecisionRecord
from switchboard.services.adjustment_engine import AdjustmentEngine, PolicyAdjustment
from switchboard.services.adjustment_store import AdjustmentStore


def _record(profile: str = "capable", status: str = "success") -> DecisionRecord:
    return DecisionRecord(
        timestamp="2024-01-01T00:00:00+00:00",
        selected_lane=profile,
        selected_backend="kodo",
        rule_name="test",
        reason="test",
        status=status,
    )


def _demote(profile: str) -> PolicyAdjustment:
    return PolicyAdjustment(profile=profile, action="demote", reason="high error rate")


def _promote(profile: str) -> PolicyAdjustment:
    return PolicyAdjustment(profile=profile, action="promote", reason="sustained health")


def _neutral(profile: str) -> PolicyAdjustment:
    return PolicyAdjustment(profile=profile, action="neutral", reason="ok")


# ---------------------------------------------------------------------------
# Basic operator controls
# ---------------------------------------------------------------------------


class TestAdjustmentStoreControls:
    def test_enabled_by_default(self) -> None:
        store = AdjustmentStore()
        assert store.enabled is True

    def test_disable_sets_enabled_false(self) -> None:
        store = AdjustmentStore()
        store.disable()
        assert store.enabled is False

    def test_enable_re_enables(self) -> None:
        store = AdjustmentStore(enabled=False)
        store.enable()
        assert store.enabled is True

    def test_reset_clears_adjustments(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_demote("capable")]
        store = AdjustmentStore(engine=engine)
        store.refresh([_record("capable", "error")] * 10)
        assert store.get_adjustment("capable") is not None
        store.reset()
        assert store.get_adjustment("capable") is None

    def test_reset_clears_last_refresh(self) -> None:
        store = AdjustmentStore()
        store.refresh([_record("capable")])
        store.reset()
        state = store.get_state()
        assert state.last_refresh is None


# ---------------------------------------------------------------------------
# refresh() and get_adjustment()
# ---------------------------------------------------------------------------


class TestAdjustmentStoreRefresh:
    def test_refresh_stores_demote(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_demote("capable")]
        store = AdjustmentStore(engine=engine)
        store.refresh([_record("capable")])
        adj = store.get_adjustment("capable")
        assert adj is not None
        assert adj.action == "demote"

    def test_refresh_does_not_store_neutral(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_neutral("capable")]
        store = AdjustmentStore(engine=engine)
        store.refresh([_record("capable")])
        assert store.get_adjustment("capable") is None

    def test_refresh_stores_promote(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_promote("fast")]
        store = AdjustmentStore(engine=engine)
        store.refresh([_record("fast")])
        adj = store.get_adjustment("fast")
        assert adj is not None
        assert adj.action == "promote"

    def test_refresh_updates_last_refresh_timestamp(self) -> None:
        store = AdjustmentStore()
        assert store.get_state().last_refresh is None
        store.refresh([])
        assert store.get_state().last_refresh is not None

    def test_get_adjustment_returns_none_for_unknown_profile(self) -> None:
        store = AdjustmentStore()
        assert store.get_adjustment("nonexistent") is None


# ---------------------------------------------------------------------------
# maybe_refresh()
# ---------------------------------------------------------------------------


class TestMaybeRefresh:
    def test_refreshes_when_never_populated(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = []
        store = AdjustmentStore(engine=engine)
        store.maybe_refresh([])
        engine.derive.assert_called_once()

    def test_does_not_refresh_when_fresh(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = []
        store = AdjustmentStore(engine=engine, ttl_seconds=300.0)
        store.refresh([])  # initial refresh
        engine.derive.reset_mock()
        store.maybe_refresh([])  # should not refresh again (TTL not expired)
        engine.derive.assert_not_called()

    def test_refreshes_when_stale(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = []
        store = AdjustmentStore(engine=engine, ttl_seconds=0.0)
        store.refresh([])  # initial
        engine.derive.reset_mock()
        store.maybe_refresh([])  # TTL=0 → always stale
        engine.derive.assert_called_once()


# ---------------------------------------------------------------------------
# get_state()
# ---------------------------------------------------------------------------


class TestAdjustmentStoreState:
    def test_state_reflects_demoted_profiles(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_demote("capable"), _demote("fast")]
        store = AdjustmentStore(engine=engine)
        store.refresh([])
        state = store.get_state()
        assert sorted(state.demoted_profiles) == ["capable", "fast"]
        assert state.promoted_profiles == []

    def test_state_reflects_promoted_profiles(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_promote("fast")]
        store = AdjustmentStore(engine=engine)
        store.refresh([])
        state = store.get_state()
        assert state.promoted_profiles == ["fast"]
        assert state.demoted_profiles == []

    def test_adjustment_count_correct(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_demote("capable"), _neutral("fast"), _promote("local")]
        store = AdjustmentStore(engine=engine)
        store.refresh([])
        state = store.get_state()
        assert state.adjustment_count == 2  # only non-neutral

    def test_get_all_adjustments_excludes_neutral(self) -> None:
        engine = MagicMock(spec=AdjustmentEngine)
        engine.derive.return_value = [_demote("capable"), _neutral("fast")]
        store = AdjustmentStore(engine=engine)
        store.refresh([])
        all_adjs = store.get_all_adjustments()
        assert len(all_adjs) == 1
        assert all_adjs[0].profile == "capable"
