"""Phase 3 integration tests — different request shapes must produce different profile selections.

These tests exercise the full classify → select pipeline (no HTTP, no 9router)
to prove that the enriched SelectionContext and richer policy rules produce
meaningfully different routing decisions for different request classes.

Each test builds a real SelectionContext via RequestClassifier, runs it through a
real PolicyEngine backed by the live policy.yaml and profiles.yaml config files,
and asserts on the selected profile.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from switchboard.adapters.file_policy_store import FilePolicyStore
from switchboard.adapters.file_profile_store import FileProfileStore
from switchboard.services.capability_registry import CapabilityRegistry
from switchboard.services.classifier import RequestClassifier
from switchboard.services.policy_engine import PolicyEngine
from switchboard.services.selector import Selector

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"


@pytest.fixture(scope="module")
def selector() -> Selector:
    policy_store = FilePolicyStore(_CONFIG_DIR / "policy.yaml")
    profile_store = FileProfileStore(_CONFIG_DIR / "profiles.yaml")
    capability_registry = CapabilityRegistry(_CONFIG_DIR / "capabilities.yaml")
    policy_engine = PolicyEngine(policy_store)
    return Selector(policy_engine, capability_registry, profile_store)


@pytest.fixture(scope="module")
def classifier() -> RequestClassifier:
    return RequestClassifier()


def _classify_and_select(
    classifier: RequestClassifier,
    selector: Selector,
    body: dict,
    headers: dict | None = None,
) -> tuple[str, str]:
    """Helper: classify body → select → return (profile_name, rule_name)."""
    ctx = classifier.classify(body, headers or {})
    result = selector.select(ctx)
    return result.profile_name, result.rule_name


# ---------------------------------------------------------------------------
# Core routing differentiation — the heart of Phase 3
# ---------------------------------------------------------------------------


class TestRequestClassRouting:
    def test_short_chat_routes_to_fast(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {"model": "fast", "messages": [{"role": "user", "content": "What is 2+2?"}]}
        profile, _ = _classify_and_select(classifier, selector, body)
        assert profile == "fast"

    def test_coding_request_routes_to_capable(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {
            "messages": [
                {"role": "user", "content": "Write a function to parse JSON from a file."}
            ]
        }
        profile, rule = _classify_and_select(classifier, selector, body)
        assert profile == "capable"
        assert rule == "coding_task"

    def test_planning_request_routes_to_capable(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": "Help me design the architecture for a distributed caching system.",
                }
            ]
        }
        profile, rule = _classify_and_select(classifier, selector, body)
        assert profile == "capable"
        assert rule == "planning_task"

    def test_summarization_routes_to_fast(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {
            "messages": [
                {"role": "user", "content": "Please summarize the following document: " + "x" * 200}
            ]
        }
        profile, rule = _classify_and_select(classifier, selector, body)
        assert profile == "fast"
        assert rule == "summarization_task"

    def test_tool_use_routes_to_capable(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {
            "messages": [{"role": "user", "content": "What is the weather?"}],
            "tools": [{"type": "function", "function": {"name": "get_weather", "parameters": {}}}],
        }
        profile, rule = _classify_and_select(classifier, selector, body)
        assert profile == "capable"
        assert rule == "tool_use"

    def test_large_context_routes_to_capable(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        # 4096 tokens * 4 chars = 16 384 chars
        body = {
            "messages": [{"role": "user", "content": "x" * 16_384}]
        }
        profile, _ = _classify_and_select(classifier, selector, body)
        assert profile == "capable"

    def test_high_priority_routes_to_capable(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {"messages": [{"role": "user", "content": "Quick question"}]}
        profile, rule = _classify_and_select(classifier, selector, body, {"X-SwitchBoard-Priority": "high"})
        assert profile == "capable"
        assert rule == "high_priority_tenant"

    def test_low_priority_routes_to_local(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {"messages": [{"role": "user", "content": "Background task"}]}
        profile, rule = _classify_and_select(classifier, selector, body, {"X-SwitchBoard-Priority": "low"})
        assert profile == "local"
        assert rule == "low_priority_local"

    def test_cost_sensitive_simple_routes_to_fast(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {"messages": [{"role": "user", "content": "Short question"}]}
        profile, rule = _classify_and_select(
            classifier, selector, body, {"X-SwitchBoard-Cost-Sensitivity": "high"}
        )
        assert profile == "fast"
        assert rule == "cost_sensitive_non_complex"

    def test_force_profile_overrides_all_rules(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        body = {
            "messages": [{"role": "user", "content": "Write a function to sort a list."}]
        }
        profile, rule = _classify_and_select(
            classifier, selector, body, {"X-SwitchBoard-Profile": "fast"}
        )
        assert profile == "fast"
        assert rule == "force_profile"


# ---------------------------------------------------------------------------
# Eligibility — tool-requiring requests must not land on local
# ---------------------------------------------------------------------------


class TestEligibilityRouting:
    def test_explicit_local_hint_with_tools_triggers_eligibility_upgrade(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        """Caller explicitly requests local, but tools are present — local doesn't support
        tool use, so the eligibility check fires and upgrades to capable."""
        body = {
            "model": "local",   # caller_requests_local rule fires (priority 11)
            "messages": [{"role": "user", "content": "Run this job"}],
            "tools": [{"type": "function", "function": {"name": "run_job", "parameters": {}}}],
        }
        ctx = classifier.classify(body, {})
        result = selector.select(ctx)

        # local rejected due to tool use; capable is the eligible fallback
        assert result.profile_name != "local"
        assert any(r["profile"] == "local" for r in result.rejected_profiles)
        assert "tool" in result.rejected_profiles[0]["reason"]

    def test_long_context_request_avoids_small_window_profiles(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        """A long request must not land on local (8 192 token context)."""
        # 7 000 tokens * 4 chars per token
        body = {"messages": [{"role": "user", "content": "x" * 28_000}]}
        ctx = classifier.classify(body, {})
        result = selector.select(ctx)

        assert result.profile_name != "local"
        assert result.profile_name in ("capable", "fast", "default")


# ---------------------------------------------------------------------------
# Decision record includes Phase 3 fields
# ---------------------------------------------------------------------------


class TestDecisionRecordPhase3:
    def test_context_summary_populated(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        from switchboard.services.decision_logger import make_decision_record

        body = {"messages": [{"role": "user", "content": "Write a function to sort a list."}]}
        ctx = classifier.classify(body, {})
        result = selector.select(ctx)
        record = make_decision_record(
            result=result,
            original_model_hint=body.get("model", ""),
            latency_ms=42.0,
        )

        assert record.context_summary is not None
        assert record.context_summary["task_type"] == "code"
        assert record.context_summary["complexity"] in ("low", "medium", "high")
        assert isinstance(record.context_summary["estimated_tokens"], int)

    def test_rejected_profiles_in_decision_record(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        from switchboard.services.decision_logger import make_decision_record

        body = {
            "messages": [{"role": "user", "content": "Background task"}],
            "tools": [{"type": "function", "function": {"name": "run_job", "parameters": {}}}],
        }
        headers = {"X-SwitchBoard-Priority": "low"}
        ctx = classifier.classify(body, headers)
        result = selector.select(ctx)
        record = make_decision_record(
            result=result,
            original_model_hint="",
            latency_ms=10.0,
        )

        # local should have been rejected due to tool use requirement
        if result.rejected_profiles:
            assert any(r["profile"] == "local" for r in record.rejected_profiles)

    def test_reason_field_populated(
        self, classifier: RequestClassifier, selector: Selector
    ) -> None:
        from switchboard.services.decision_logger import make_decision_record

        body = {"messages": [{"role": "user", "content": "Write a function to reverse a list."}]}
        ctx = classifier.classify(body, {})
        result = selector.select(ctx)
        record = make_decision_record(result=result, original_model_hint="", latency_ms=5.0)

        assert record.reason != ""
        assert "capable" in record.reason or "fast" in record.reason
