# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""Phase 2: SwitchBoard emits CxRP-shaped LaneDecision at its boundary.

Tests that the SB → CxRP mapper produces wire output conforming to CxRP's
JSON Schema, and that SB has not grown any execution/adapter behavior.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from cxrp.contracts import LaneDecision as CxrpLaneDecision
from cxrp.validation.json_schema import validate_contract
from cxrp.vocabulary.lane import LaneType
from operations_center.contracts import LaneDecision as OcLaneDecision
from operations_center.contracts.enums import BackendName, LaneName

from switchboard.adapters.cxrp_mapper import to_cxrp_lane_decision


def _serialize_for_schema(decision: CxrpLaneDecision) -> dict:
    """Render an CxRP LaneDecision dataclass into the JSON-shaped dict the
    schema validates. Mirrors BaseContract.to_dict() but also normalises
    nested LaneAlternative dataclasses."""
    payload = decision.to_dict()
    payload["alternatives"] = [asdict(alt) for alt in decision.alternatives]
    for alt in payload["alternatives"]:
        alt["lane"] = alt["lane"].value if hasattr(alt["lane"], "value") else alt["lane"]
    payload["lane"] = payload["lane"].value if hasattr(payload["lane"], "value") else payload["lane"]
    return payload


def _make_oc_decision() -> OcLaneDecision:
    return OcLaneDecision(
        proposal_id="prop-001",
        selected_lane=LaneName.CLAUDE_CLI,
        selected_backend=BackendName.KODO,
        confidence=0.92,
        policy_rule_matched="bugfix-low-risk",
        rationale="task_type=bug_fix + risk=low → claude_cli via kodo",
        alternatives_considered=[LaneName.CODEX_CLI],
    )


def test_mapper_returns_ecp_lane_decision():
    cxrp = to_cxrp_lane_decision(_make_oc_decision())
    assert isinstance(cxrp, CxrpLaneDecision)
    assert cxrp.contract_kind == "lane_decision"
    assert cxrp.schema_version == "0.2"


def test_mapper_separates_category_from_executor_and_backend():
    cxrp = to_cxrp_lane_decision(_make_oc_decision())
    assert cxrp.lane == LaneType.CODING_AGENT
    assert cxrp.executor == "claude_cli"
    assert cxrp.backend == "kodo"


def test_mapper_preserves_identifiers_and_rationale():
    oc = _make_oc_decision()
    cxrp = to_cxrp_lane_decision(oc)
    assert cxrp.proposal_id == oc.proposal_id
    assert cxrp.decision_id == oc.decision_id
    assert cxrp.rationale == oc.rationale
    assert cxrp.confidence == oc.confidence


def test_mapper_emits_structured_alternatives():
    cxrp = to_cxrp_lane_decision(_make_oc_decision())
    assert len(cxrp.alternatives) == 1
    alt = cxrp.alternatives[0]
    assert alt.lane == LaneType.CODING_AGENT
    assert alt.executor == "codex_cli"


def test_mapper_output_validates_against_ecp_schema():
    cxrp = to_cxrp_lane_decision(_make_oc_decision())
    payload = _serialize_for_schema(cxrp)
    validate_contract("lane_decision", payload)


def test_mapper_confidence_stays_within_bounds():
    oc = _make_oc_decision()
    cxrp = to_cxrp_lane_decision(oc)
    assert 0.0 <= cxrp.confidence <= 1.0


def test_mapper_rejects_out_of_bounds_confidence():
    """Both OC's pydantic and CxRP's dataclass enforce 0 <= confidence <= 1."""
    with pytest.raises(ValueError):
        OcLaneDecision(
            proposal_id="x",
            selected_lane=LaneName.CLAUDE_CLI,
            selected_backend=BackendName.KODO,
            confidence=1.5,
        )
    with pytest.raises(ValueError, match="confidence must be between"):
        CxrpLaneDecision(confidence=1.5)


def test_mapper_carries_policy_rule_in_metadata():
    cxrp = to_cxrp_lane_decision(_make_oc_decision())
    assert cxrp.metadata["policy_rule_matched"] == "bugfix-low-risk"


def test_mapper_extra_metadata_is_merged():
    cxrp = to_cxrp_lane_decision(
        _make_oc_decision(), extra_metadata={"policy_version": "2026.04.28"}
    )
    assert cxrp.metadata["policy_version"] == "2026.04.28"
    assert cxrp.metadata["policy_rule_matched"] == "bugfix-low-risk"


def test_switchboard_does_not_import_execution_or_adapter_modules():
    """Boundary invariant: SwitchBoard does not invoke execution or providers."""
    forbidden_substrings = (
        "operations_center.execution",
        "operations_center.backends",
        "operations_center.adapters",
        "operations_center.openclaw_shell",
    )
    src_root = Path(__file__).resolve().parents[2] / "src" / "switchboard"
    offenders = []
    for py_file in src_root.rglob("*.py"):
        text = py_file.read_text()
        for needle in forbidden_substrings:
            if needle in text:
                offenders.append(f"{py_file}: {needle}")
    assert not offenders, "SwitchBoard imports execution-side OC modules:\n" + "\n".join(offenders)


def test_switchboard_does_not_emit_execution_request_or_result_types():
    """Mapper should not produce ExecutionRequest or ExecutionResult shapes."""
    cxrp = to_cxrp_lane_decision(_make_oc_decision())
    payload = _serialize_for_schema(cxrp)
    assert payload["contract_kind"] == "lane_decision"
    forbidden_kinds = {"execution_request", "execution_result", "task_proposal"}
    assert payload["contract_kind"] not in forbidden_kinds - {"lane_decision"}
    serialized = json.dumps(payload)
    assert "execution_request" not in serialized
    assert "execution_result" not in serialized
