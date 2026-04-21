"""Unit tests for RequestClassifier."""

import pytest

from switchboard.services.classifier import (
    RequestClassifier,
    _estimate_tokens,
    _infer_complexity,
    _infer_task_type,
)


@pytest.fixture()
def classifier() -> RequestClassifier:
    return RequestClassifier()


# ---------------------------------------------------------------------------
# Header override tests
# ---------------------------------------------------------------------------


class TestHeaderOverrides:
    def test_force_profile_from_header(self, classifier: RequestClassifier) -> None:
        body = {"messages": [{"role": "user", "content": "hi"}]}
        headers = {"X-SwitchBoard-Profile": "capable"}
        ctx = classifier.classify(body, headers)
        assert ctx.force_profile == "capable"

    def test_tenant_id_from_header(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        headers = {"X-SwitchBoard-Tenant-ID": "acme-corp"}
        ctx = classifier.classify(body, headers)
        assert ctx.tenant_id == "acme-corp"

    def test_priority_from_header(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        headers = {"x-switchboard-priority": "high"}  # lowercase header name
        ctx = classifier.classify(body, headers)
        assert ctx.priority == "high"

    def test_no_headers_gives_none_values(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        ctx = classifier.classify(body, {})
        assert ctx.force_profile is None
        assert ctx.tenant_id is None
        assert ctx.priority is None

    def test_header_names_are_case_insensitive(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        headers = {
            "X-SWITCHBOARD-TENANT-ID": "uppercase-tenant",
            "x-switchboard-profile": "local",
        }
        ctx = classifier.classify(body, headers)
        assert ctx.tenant_id == "uppercase-tenant"
        assert ctx.force_profile == "local"


# ---------------------------------------------------------------------------
# Body heuristic tests
# ---------------------------------------------------------------------------


class TestBodyHeuristics:
    def test_model_hint_extracted(self, classifier: RequestClassifier) -> None:
        body = {"model": "gpt-4o", "messages": []}
        ctx = classifier.classify(body, {})
        assert ctx.model_hint == "gpt-4o"

    def test_model_hint_defaults_to_empty_string(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        ctx = classifier.classify(body, {})
        assert ctx.model_hint == ""

    def test_stream_true(self, classifier: RequestClassifier) -> None:
        body = {"messages": [], "stream": True}
        ctx = classifier.classify(body, {})
        assert ctx.stream is True

    def test_stream_false_by_default(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        ctx = classifier.classify(body, {})
        assert ctx.stream is False

    def test_max_tokens_extracted(self, classifier: RequestClassifier) -> None:
        body = {"messages": [], "max_tokens": 512}
        ctx = classifier.classify(body, {})
        assert ctx.max_tokens == 512

    def test_max_completion_tokens_alias(self, classifier: RequestClassifier) -> None:
        body = {"messages": [], "max_completion_tokens": 1024}
        ctx = classifier.classify(body, {})
        assert ctx.max_tokens == 1024

    def test_temperature_extracted(self, classifier: RequestClassifier) -> None:
        body = {"messages": [], "temperature": 0.2}
        ctx = classifier.classify(body, {})
        assert ctx.temperature == pytest.approx(0.2)

    def test_tools_present_when_tools_list_nonempty(self, classifier: RequestClassifier) -> None:
        body = {
            "messages": [],
            "tools": [{"type": "function", "function": {"name": "foo"}}],
        }
        ctx = classifier.classify(body, {})
        assert ctx.tools_present is True

    def test_tools_not_present_when_tools_absent(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        ctx = classifier.classify(body, {})
        assert ctx.tools_present is False

    def test_tools_not_present_when_tools_empty_list(self, classifier: RequestClassifier) -> None:
        body = {"messages": [], "tools": []}
        ctx = classifier.classify(body, {})
        assert ctx.tools_present is False

    def test_estimated_tokens_calculated(self, classifier: RequestClassifier) -> None:
        # 40 chars / 4 = 10 tokens
        body = {
            "messages": [
                {"role": "user", "content": "a" * 40},
            ]
        }
        ctx = classifier.classify(body, {})
        assert ctx.estimated_tokens == 10

    def test_estimated_tokens_minimum_is_one(self, classifier: RequestClassifier) -> None:
        body = {"messages": []}
        ctx = classifier.classify(body, {})
        assert ctx.estimated_tokens >= 1

    def test_multipart_content_tokens_summed(self, classifier: RequestClassifier) -> None:
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "A" * 80},
                        {"type": "image_url", "image_url": {"url": "data:..."}},
                    ],
                }
            ]
        }
        ctx = classifier.classify(body, {})
        # 80 chars / 4 = 20 tokens (image part has no text)
        assert ctx.estimated_tokens == 20

    def test_extra_captures_response_format(self, classifier: RequestClassifier) -> None:
        body = {
            "messages": [],
            "response_format": {"type": "json_object"},
        }
        ctx = classifier.classify(body, {})
        assert ctx.extra.get("response_format") == {"type": "json_object"}


# ---------------------------------------------------------------------------
# Standalone helper tests
# ---------------------------------------------------------------------------


class TestEstimateTokens:
    def test_empty_messages(self) -> None:
        assert _estimate_tokens([]) >= 1

    def test_simple_string_content(self) -> None:
        msgs = [{"role": "user", "content": "x" * 100}]
        assert _estimate_tokens(msgs) == 25  # 100 / 4

    def test_multiple_messages_summed(self) -> None:
        msgs = [
            {"role": "system", "content": "s" * 40},
            {"role": "user", "content": "u" * 40},
        ]
        assert _estimate_tokens(msgs) == 20  # 80 / 4

    def test_non_string_content_ignored_gracefully(self) -> None:
        msgs = [{"role": "user", "content": None}]
        result = _estimate_tokens(msgs)
        assert result >= 1  # should not raise


# ---------------------------------------------------------------------------
# Phase 3 — task_type inference
# ---------------------------------------------------------------------------


class TestTaskTypeInference:
    def test_code_fence_signals_code(self) -> None:
        msgs = [{"role": "user", "content": "Please review this:\n```python\ndef foo(): pass\n```"}]
        assert _infer_task_type(msgs) == "code"

    def test_implement_phrase_signals_code(self) -> None:
        msgs = [{"role": "user", "content": "Can you implement a binary search function?"}]
        assert _infer_task_type(msgs) == "code"

    def test_refactor_phrase_signals_code(self) -> None:
        msgs = [{"role": "user", "content": "Refactor this class to use dataclasses."}]
        assert _infer_task_type(msgs) == "code"

    def test_write_a_function_signals_code(self) -> None:
        msgs = [{"role": "user", "content": "Write a function that reverses a string."}]
        assert _infer_task_type(msgs) == "code"

    def test_architecture_signals_planning(self) -> None:
        msgs = [{"role": "user", "content": "Help me design the architecture for a microservices system."}]
        assert _infer_task_type(msgs) == "planning"

    def test_how_should_i_signals_planning(self) -> None:
        msgs = [{"role": "user", "content": "How should I approach building this feature?"}]
        assert _infer_task_type(msgs) == "planning"

    def test_summarize_signals_summarization(self) -> None:
        msgs = [{"role": "user", "content": "Please summarize this document for me."}]
        assert _infer_task_type(msgs) == "summarization"

    def test_tldr_signals_summarization(self) -> None:
        msgs = [{"role": "user", "content": "tldr of this article please"}]
        assert _infer_task_type(msgs) == "summarization"

    def test_plain_question_is_chat(self) -> None:
        msgs = [{"role": "user", "content": "What is the capital of France?"}]
        assert _infer_task_type(msgs) == "chat"

    def test_empty_messages_is_chat(self) -> None:
        assert _infer_task_type([]) == "chat"

    def test_code_detected_before_planning(self) -> None:
        # A message asking to "implement a plan" should be "code" not "planning"
        msgs = [{"role": "user", "content": "implement this step-by-step plan in code"}]
        assert _infer_task_type(msgs) == "code"


# ---------------------------------------------------------------------------
# Phase 3 — complexity inference
# ---------------------------------------------------------------------------


class TestComplexityInference:
    def test_low_complexity_short_few_messages(self) -> None:
        assert _infer_complexity(100, 1, False) == "low"

    def test_medium_complexity_moderate_tokens(self) -> None:
        assert _infer_complexity(600, 2, False) == "medium"

    def test_medium_complexity_many_messages(self) -> None:
        assert _infer_complexity(100, 5, False) == "medium"

    def test_high_complexity_many_tokens(self) -> None:
        assert _infer_complexity(4000, 2, False) == "high"

    def test_high_complexity_many_messages(self) -> None:
        assert _infer_complexity(100, 10, False) == "high"

    def test_high_complexity_tools_present(self) -> None:
        assert _infer_complexity(100, 1, True) == "high"

    def test_boundary_500_tokens_is_medium(self) -> None:
        assert _infer_complexity(501, 1, False) == "medium"

    def test_boundary_3000_tokens_is_high(self) -> None:
        assert _infer_complexity(3001, 1, False) == "high"


# ---------------------------------------------------------------------------
# Phase 3 — requires_long_context and requires_tools
# ---------------------------------------------------------------------------


class TestRequiresFlags:
    def test_requires_long_context_above_threshold(self) -> None:
        body = {"messages": [{"role": "user", "content": "x" * (6000 * 4 + 4)}]}
        ctx = RequestClassifier().classify(body, {})
        assert ctx.requires_long_context is True

    def test_requires_long_context_below_threshold(self) -> None:
        body = {"messages": [{"role": "user", "content": "hello"}]}
        ctx = RequestClassifier().classify(body, {})
        assert ctx.requires_long_context is False

    def test_requires_tools_when_tools_present(self) -> None:
        body = {
            "messages": [{"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "foo"}}],
        }
        ctx = RequestClassifier().classify(body, {})
        assert ctx.requires_tools is True

    def test_requires_tools_false_when_no_tools(self) -> None:
        body = {"messages": [{"role": "user", "content": "hi"}]}
        ctx = RequestClassifier().classify(body, {})
        assert ctx.requires_tools is False


# ---------------------------------------------------------------------------
# Phase 3 — cost_sensitivity and latency_sensitivity headers
# ---------------------------------------------------------------------------


class TestSensitivityHeaders:
    def test_cost_sensitivity_from_header(self) -> None:
        body = {"messages": []}
        ctx = RequestClassifier().classify(body, {"X-SwitchBoard-Cost-Sensitivity": "high"})
        assert ctx.cost_sensitivity == "high"

    def test_latency_sensitivity_from_header(self) -> None:
        body = {"messages": []}
        ctx = RequestClassifier().classify(body, {"X-SwitchBoard-Latency-Sensitivity": "low"})
        assert ctx.latency_sensitivity == "low"

    def test_streaming_implies_high_latency_sensitivity(self) -> None:
        body = {"messages": [], "stream": True}
        ctx = RequestClassifier().classify(body, {})
        assert ctx.latency_sensitivity == "high"

    def test_header_overrides_stream_derived_latency_sensitivity(self) -> None:
        body = {"messages": [], "stream": True}
        ctx = RequestClassifier().classify(body, {"X-SwitchBoard-Latency-Sensitivity": "low"})
        assert ctx.latency_sensitivity == "low"

    def test_no_sensitivity_headers_gives_none(self) -> None:
        body = {"messages": []}
        ctx = RequestClassifier().classify(body, {})
        assert ctx.cost_sensitivity is None
        # latency_sensitivity is None only if stream is also False
        assert ctx.latency_sensitivity is None
