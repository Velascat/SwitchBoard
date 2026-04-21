"""Unit tests for Phase 8 classifier additions: analysis task type + structured output."""

from __future__ import annotations

from switchboard.services.classifier import (
    RequestClassifier,
    _infer_structured_output,
    _infer_task_type,
)


def _msgs(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


# ---------------------------------------------------------------------------
# Analysis task type
# ---------------------------------------------------------------------------


class TestAnalysisTaskType:
    def test_detects_analyze(self) -> None:
        assert _infer_task_type(_msgs("Can you analyze this dataset?")) == "analysis"

    def test_detects_analyse_british(self) -> None:
        assert _infer_task_type(_msgs("Please analyse the following log")) == "analysis"

    def test_detects_root_cause(self) -> None:
        assert _infer_task_type(_msgs("Find the root cause of this failure")) == "analysis"

    def test_detects_compare_contrast(self) -> None:
        assert _infer_task_type(_msgs("Compare and contrast these two approaches")) == "analysis"

    def test_detects_pros_and_cons(self) -> None:
        assert _infer_task_type(_msgs("What are the pros and cons of each option?")) == "analysis"

    def test_detects_tradeoffs(self) -> None:
        assert _infer_task_type(_msgs("What are the tradeoffs between approach A and B?")) == "analysis"

    def test_detects_evaluate(self) -> None:
        assert _infer_task_type(_msgs("Evaluate the performance of this algorithm")) == "analysis"

    def test_code_beats_analysis(self) -> None:
        # Code fence takes priority over analysis phrase
        assert _infer_task_type(_msgs("```python\nanalyze(x)\n```")) == "code"

    def test_analysis_beats_planning(self) -> None:
        # "analyze" should be classified as analysis, not planning
        result = _infer_task_type(_msgs("analyze the architecture and design a plan"))
        assert result == "analysis"


# ---------------------------------------------------------------------------
# Full classifier: task_type = analysis
# ---------------------------------------------------------------------------


class TestClassifierAnalysisIntegration:
    def setup_method(self) -> None:
        self.classifier = RequestClassifier()

    def test_classify_returns_analysis_task_type(self) -> None:
        body = {"messages": [{"role": "user", "content": "Analyze these metrics and find trends"}]}
        ctx = self.classifier.classify(body, {})
        assert ctx.task_type == "analysis"

    def test_classify_four_types_all_distinguishable(self) -> None:
        cases = [
            ("write a function to sort a list", "code"),
            ("Analyze the failure patterns", "analysis"),
            ("create a plan for the migration", "planning"),
            ("summarize this document", "summarization"),
            ("Hello, how are you?", "chat"),
        ]
        for text, expected in cases:
            body = {"messages": [{"role": "user", "content": text}]}
            ctx = self.classifier.classify(body, {})
            assert ctx.task_type == expected, f"Expected {expected!r} for text: {text!r}"


# ---------------------------------------------------------------------------
# Structured output detection
# ---------------------------------------------------------------------------


class TestInferStructuredOutput:
    def test_none_response_format_returns_false(self) -> None:
        assert _infer_structured_output(None) is False

    def test_non_dict_returns_false(self) -> None:
        assert _infer_structured_output("json") is False

    def test_json_object_type_returns_true(self) -> None:
        assert _infer_structured_output({"type": "json_object"}) is True

    def test_json_schema_type_returns_true(self) -> None:
        assert _infer_structured_output({"type": "json_schema", "json_schema": {}}) is True

    def test_text_type_returns_false(self) -> None:
        assert _infer_structured_output({"type": "text"}) is False

    def test_missing_type_key_returns_false(self) -> None:
        assert _infer_structured_output({"format": "json"}) is False


class TestClassifierStructuredOutput:
    def setup_method(self) -> None:
        self.classifier = RequestClassifier()

    def test_json_object_sets_requires_structured_output(self) -> None:
        body = {
            "messages": [{"role": "user", "content": "Give me JSON"}],
            "response_format": {"type": "json_object"},
        }
        ctx = self.classifier.classify(body, {})
        assert ctx.requires_structured_output is True

    def test_json_schema_sets_requires_structured_output(self) -> None:
        body = {
            "messages": [{"role": "user", "content": "Give me JSON"}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "result"}},
        }
        ctx = self.classifier.classify(body, {})
        assert ctx.requires_structured_output is True

    def test_no_response_format_leaves_false(self) -> None:
        body = {"messages": [{"role": "user", "content": "Hello"}]}
        ctx = self.classifier.classify(body, {})
        assert ctx.requires_structured_output is False

    def test_text_response_format_leaves_false(self) -> None:
        body = {
            "messages": [{"role": "user", "content": "Hello"}],
            "response_format": {"type": "text"},
        }
        ctx = self.classifier.classify(body, {})
        assert ctx.requires_structured_output is False

    def test_response_format_stored_in_extra(self) -> None:
        fmt = {"type": "json_object"}
        body = {"messages": [{"role": "user", "content": "x"}], "response_format": fmt}
        ctx = self.classifier.classify(body, {})
        assert ctx.extra.get("response_format") == fmt
