"""Integration tests for Phase 7 adaptive policy.

Tests:
  - GET  /admin/adaptive         — state inspection
  - POST /admin/adaptive/enable  — enable adaptation
  - POST /admin/adaptive/disable — disable adaptation
  - POST /admin/adaptive/reset   — clear adjustments
  - POST /admin/adaptive/refresh — recompute from decision log

  - Selector integration: demoted profile is redirected
  - Decision record carries adjustment_applied / adjustment_reason trace
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from switchboard.app import create_app
from switchboard.domain.decision_record import DecisionRecord
from switchboard.domain.selection_context import SelectionContext
from switchboard.domain.selection_result import SelectionResult
from switchboard.services.adjustment_engine import PolicyAdjustment
from switchboard.services.adjustment_store import AdjustmentStore
from switchboard.services.decision_logger import DecisionLogger

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _error_record(profile: str = "capable") -> DecisionRecord:
    return DecisionRecord(
        timestamp="2024-01-01T00:00:00+00:00",
        selected_profile=profile,
        downstream_model="gpt-4o",
        rule_name="default",
        reason="test",
        status="error",
        error_category="upstream_error",
    )


def _success_record(profile: str = "capable", latency_ms: float = 200.0) -> DecisionRecord:
    return DecisionRecord(
        timestamp="2024-01-01T00:00:00+00:00",
        selected_profile=profile,
        downstream_model="gpt-4o",
        rule_name="default",
        reason="test",
        status="success",
        latency_ms=latency_ms,
    )


@pytest.fixture()
async def adaptive_client():
    """ASGI test client with a real AdjustmentStore and DecisionLogger."""
    app = create_app()

    decision_log = DecisionLogger(log_path=None)
    adjustment_store = AdjustmentStore()

    mock_gateway = MagicMock()
    mock_gateway.close = AsyncMock()
    mock_settings = MagicMock()
    mock_settings.port = 20401
    mock_settings.nine_router_url = "http://localhost:20128"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        app.state.settings = mock_settings
        app.state.decision_log = decision_log
        app.state.decision_logger = decision_log
        app.state.adjustment_store = adjustment_store
        app.state.gateway = mock_gateway
        # Other state entries tests may not need
        app.state.classifier = MagicMock()
        app.state.selector = MagicMock()
        app.state.forwarder = MagicMock()
        app.state.profile_store = MagicMock()
        yield client, decision_log, adjustment_store


# ---------------------------------------------------------------------------
# GET /admin/adaptive — state inspection
# ---------------------------------------------------------------------------


class TestAdaptiveStateEndpoint:
    async def test_initial_state_enabled_no_adjustments(self, adaptive_client) -> None:
        client, _, _ = adaptive_client
        resp = await client.get("/admin/adaptive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["adjustment_count"] == 0
        assert data["demoted_profiles"] == []
        assert data["promoted_profiles"] == []
        assert data["last_refresh"] is None

    async def test_state_shows_demoted_after_refresh(self, adaptive_client) -> None:
        client, decision_log, adjustment_store = adaptive_client
        # Seed decision log with 10 errors for "capable"
        for _ in range(10):
            decision_log.append(_error_record("capable"))

        resp = await client.post("/admin/adaptive/refresh?n=50")
        assert resp.status_code == 200
        data = resp.json()
        assert "capable" in data["demoted_profiles"]

    async def test_state_shows_window_size(self, adaptive_client) -> None:
        client, _, _ = adaptive_client
        resp = await client.get("/admin/adaptive")
        assert resp.status_code == 200
        data = resp.json()
        assert data["window_size"] == 200  # default

    async def test_state_includes_adjustment_details(self, adaptive_client) -> None:
        client, decision_log, adjustment_store = adaptive_client
        for _ in range(10):
            decision_log.append(_error_record("capable"))
        await client.post("/admin/adaptive/refresh?n=50")

        resp = await client.get("/admin/adaptive")
        data = resp.json()
        adjustments = data["adjustments"]
        assert any(a["profile"] == "capable" and a["action"] == "demote" for a in adjustments)
        # Each adjustment has a reason
        for adj in adjustments:
            assert adj["reason"]


# ---------------------------------------------------------------------------
# POST /admin/adaptive/enable and /disable
# ---------------------------------------------------------------------------


class TestAdaptiveEnableDisable:
    async def test_disable_returns_enabled_false(self, adaptive_client) -> None:
        client, _, _ = adaptive_client
        resp = await client.post("/admin/adaptive/disable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_enable_returns_enabled_true(self, adaptive_client) -> None:
        client, _, _ = adaptive_client
        await client.post("/admin/adaptive/disable")
        resp = await client.post("/admin/adaptive/enable")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_get_state_reflects_disable(self, adaptive_client) -> None:
        client, _, _ = adaptive_client
        await client.post("/admin/adaptive/disable")
        resp = await client.get("/admin/adaptive")
        assert resp.json()["enabled"] is False


# ---------------------------------------------------------------------------
# POST /admin/adaptive/reset
# ---------------------------------------------------------------------------


class TestAdaptiveReset:
    async def test_reset_clears_adjustments(self, adaptive_client) -> None:
        client, decision_log, adjustment_store = adaptive_client
        for _ in range(10):
            decision_log.append(_error_record("capable"))
        await client.post("/admin/adaptive/refresh?n=50")

        resp = await client.post("/admin/adaptive/reset")
        assert resp.status_code == 200
        data = resp.json()
        assert data["adjustment_count"] == 0
        assert data["demoted_profiles"] == []

    async def test_reset_clears_last_refresh(self, adaptive_client) -> None:
        client, decision_log, _ = adaptive_client
        decision_log.append(_success_record("capable"))
        await client.post("/admin/adaptive/refresh?n=50")
        await client.post("/admin/adaptive/reset")
        resp = await client.get("/admin/adaptive")
        assert resp.json()["last_refresh"] is None


# ---------------------------------------------------------------------------
# POST /admin/adaptive/refresh
# ---------------------------------------------------------------------------


class TestAdaptiveRefresh:
    async def test_refresh_uses_decision_log(self, adaptive_client) -> None:
        client, decision_log, _ = adaptive_client
        # 10 errors → demote threshold
        for _ in range(10):
            decision_log.append(_error_record("fast"))

        resp = await client.post("/admin/adaptive/refresh?n=100")
        assert resp.status_code == 200
        data = resp.json()
        assert "fast" in data["demoted_profiles"]

    async def test_refresh_updates_last_refresh_timestamp(self, adaptive_client) -> None:
        client, _, _ = adaptive_client
        resp = await client.post("/admin/adaptive/refresh?n=50")
        assert resp.json()["last_refresh"] is not None

    async def test_refresh_with_only_successes_no_demotions(self, adaptive_client) -> None:
        client, decision_log, _ = adaptive_client
        for _ in range(10):
            decision_log.append(_success_record("capable"))
        resp = await client.post("/admin/adaptive/refresh?n=50")
        assert resp.json()["demoted_profiles"] == []


# ---------------------------------------------------------------------------
# Decision record adjustment trace
# ---------------------------------------------------------------------------


class TestAdjustmentTraceInDecisionRecord:
    def test_decision_record_has_adjustment_fields(self) -> None:
        record = DecisionRecord(
            timestamp="2024-01-01T00:00:00+00:00",
            selected_profile="fast",
            downstream_model="gpt-4o-mini",
            rule_name="adaptive_demote",
            reason="test",
        )
        assert record.adjustment_applied is False
        assert record.adjustment_reason is None

    def test_decision_record_with_adjustment_applied(self) -> None:
        record = DecisionRecord(
            timestamp="2024-01-01T00:00:00+00:00",
            selected_profile="fast",
            downstream_model="gpt-4o-mini",
            rule_name="adaptive_demote",
            reason="test",
            adjustment_applied=True,
            adjustment_reason="error rate 45% over 10 requests",
        )
        assert record.adjustment_applied is True
        assert "error rate" in record.adjustment_reason

    def test_make_decision_record_carries_adjustment_fields(self) -> None:
        from switchboard.services.decision_logger import make_decision_record

        ctx = SelectionContext(
            messages=[{"role": "user", "content": "hi"}], model_hint="capable"
        )
        result = SelectionResult(
            profile="fast",
            profile_name="fast",
            downstream_model="gpt-4o-mini",
            rule_name="adaptive_demote",
            reason="rule:adaptive_demote → profile:fast",
            context=ctx,
            adjustment_applied=True,
            adjustment_reason="high error rate",
        )
        record = make_decision_record(
            result=result,
            original_model_hint="capable",
        )
        assert record.adjustment_applied is True
        assert record.adjustment_reason == "high error rate"
        assert record.rule_name == "adaptive_demote"


# ---------------------------------------------------------------------------
# Selector integration — adaptive redirection
# ---------------------------------------------------------------------------


class TestSelectorAdaptiveRedirection:
    def _make_selector_with_adjustment(
        self,
        policy_profile: str,
        demoted: list[str],
        available_profiles: dict,
    ):
        from switchboard.services.selector import Selector

        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = (policy_profile, "default_rule")

        capability_registry = MagicMock()
        capability_registry.all_profiles.return_value = available_profiles
        capability_registry.resolve_profile.side_effect = lambda p: available_profiles.get(p, {}).get("downstream_model", p)

        adjustment_store = AdjustmentStore()
        for profile in demoted:
            # Inject a demote directly
            adjustment_store._adjustments[profile] = PolicyAdjustment(
                profile=profile, action="demote", reason="test demotion"
            )
        adjustment_store._last_refresh = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

        return Selector(policy_engine, capability_registry, adjustment_store=adjustment_store)

    def test_selector_redirects_demoted_profile(self) -> None:
        available = {
            "capable": {"downstream_model": "gpt-4o"},
            "fast": {"downstream_model": "gpt-4o-mini"},
        }
        selector = self._make_selector_with_adjustment(
            policy_profile="capable",
            demoted=["capable"],
            available_profiles=available,
        )
        ctx = SelectionContext(
            messages=[{"role": "user", "content": "hi"}], model_hint="capable"
        )
        result = selector.select(ctx)
        assert result.profile_name == "fast"
        assert result.rule_name == "adaptive_demote"
        assert result.adjustment_applied is True
        assert result.adjustment_reason is not None

    def test_selector_no_redirection_when_not_demoted(self) -> None:
        available = {
            "capable": {"downstream_model": "gpt-4o"},
            "fast": {"downstream_model": "gpt-4o-mini"},
        }
        selector = self._make_selector_with_adjustment(
            policy_profile="capable",
            demoted=[],
            available_profiles=available,
        )
        ctx = SelectionContext(
            messages=[{"role": "user", "content": "hi"}], model_hint="capable"
        )
        result = selector.select(ctx)
        assert result.profile_name == "capable"
        assert result.adjustment_applied is False

    def test_selector_force_profile_bypasses_adjustment(self) -> None:
        available = {
            "capable": {"downstream_model": "gpt-4o"},
            "fast": {"downstream_model": "gpt-4o-mini"},
        }
        from switchboard.services.selector import Selector

        policy_engine = MagicMock()
        policy_engine.select_profile.return_value = ("capable", "force_profile")

        capability_registry = MagicMock()
        capability_registry.all_profiles.return_value = available
        capability_registry.resolve_profile.side_effect = lambda p: available.get(p, {}).get("downstream_model", p)

        adjustment_store = AdjustmentStore()
        adjustment_store._adjustments["capable"] = PolicyAdjustment(
            profile="capable", action="demote", reason="test"
        )

        selector = Selector(policy_engine, capability_registry, adjustment_store=adjustment_store)
        ctx = SelectionContext(
            messages=[{"role": "user", "content": "hi"}], model_hint="capable"
        )
        result = selector.select(ctx)
        assert result.profile_name == "capable"
        assert result.adjustment_applied is False

    def test_selector_no_redirection_when_disabled(self) -> None:
        available = {
            "capable": {"downstream_model": "gpt-4o"},
            "fast": {"downstream_model": "gpt-4o-mini"},
        }
        selector = self._make_selector_with_adjustment(
            policy_profile="capable",
            demoted=["capable"],
            available_profiles=available,
        )
        selector._adjustment_store.disable()
        ctx = SelectionContext(
            messages=[{"role": "user", "content": "hi"}], model_hint="capable"
        )
        result = selector.select(ctx)
        assert result.profile_name == "capable"
        assert result.adjustment_applied is False

    def test_selector_no_alternative_stays_on_demoted(self) -> None:
        """If all profiles are demoted, stay on original (fail-open)."""
        available = {
            "capable": {"downstream_model": "gpt-4o"},
        }
        selector = self._make_selector_with_adjustment(
            policy_profile="capable",
            demoted=["capable"],
            available_profiles=available,
        )
        ctx = SelectionContext(
            messages=[{"role": "user", "content": "hi"}], model_hint="capable"
        )
        result = selector.select(ctx)
        # No alternative → stays on capable
        assert result.profile_name == "capable"
        assert result.adjustment_applied is False
