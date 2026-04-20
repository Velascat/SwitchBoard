"""Unit tests for RequestClassifier."""

import pytest

from switchboard.services.classifier import RequestClassifier, _estimate_tokens


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
