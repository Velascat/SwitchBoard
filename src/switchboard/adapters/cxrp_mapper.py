# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""Map SwitchBoard's internal LaneDecision (rich, Pydantic) to CxRP's
canonical LaneDecision envelope.

SwitchBoard's selector emits an `operations_center.contracts.LaneDecision`
populated with OC's narrowed enums (LaneName, BackendName). CxRP defines the
*envelope*: an abstract `lane: LaneType` category plus open-string `executor`
and `backend` fields that consumers may narrow internally.

This mapper is the boundary translator. It does not invoke selection,
adapters, or providers — it only restructures an already-produced decision
into the wire shape CxRP guarantees.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from cxrp.contracts import LaneAlternative
from cxrp.contracts import LaneDecision as CxrpLaneDecision
from cxrp.vocabulary.lane import LaneType
from operations_center.contracts import LaneDecision as OcLaneDecision

_OC_LANE_TO_ECP_CATEGORY: dict[str, LaneType] = {
    "claude_cli": LaneType.CODING_AGENT,
    "codex_cli": LaneType.CODING_AGENT,
    "aider_local": LaneType.CODING_AGENT,
}


def _category_for(oc_lane_value: str) -> LaneType:
    return _OC_LANE_TO_ECP_CATEGORY.get(oc_lane_value, LaneType.CODING_AGENT)


def to_cxrp_lane_decision(
    oc_decision: OcLaneDecision,
    *,
    extra_metadata: dict[str, Any] | None = None,
) -> CxrpLaneDecision:
    """Translate an OC LaneDecision into the CxRP envelope shape.

    OC's `selected_lane` (e.g. ``claude_cli``) becomes CxRP's `executor`.
    OC's `selected_backend` (e.g. ``kodo``) becomes CxRP's `backend`.
    The abstract CxRP `lane` category is derived from the OC lane via
    `_OC_LANE_TO_ECP_CATEGORY`.
    """
    metadata: dict[str, Any] = {
        "policy_rule_matched": oc_decision.policy_rule_matched,
    }
    if extra_metadata:
        metadata.update(extra_metadata)

    # Schema 0.3 — backend/executor are typed CxRP enums on the wire.
    # Convert OC's same-valued enums by .value lookup.
    from cxrp.contracts import BackendName as CxrpBackendName, ExecutorName as CxrpExecutorName
    from cxrp.contracts.execution_target import ExecutionTargetEnvelope
    cxrp_lane = _category_for(oc_decision.selected_lane.value)
    cxrp_executor = CxrpExecutorName(oc_decision.selected_lane.value)
    cxrp_backend = CxrpBackendName(oc_decision.selected_backend.value)
    envelope = ExecutionTargetEnvelope(
        lane=cxrp_lane, backend=cxrp_backend, executor=cxrp_executor,
        runtime_binding=None,  # SB doesn't bind runtime; OC does
    )
    return CxrpLaneDecision(
        decision_id=oc_decision.decision_id,
        proposal_id=oc_decision.proposal_id,
        created_at=oc_decision.decided_at,
        metadata=metadata,
        lane=cxrp_lane,
        executor=cxrp_executor,
        backend=cxrp_backend,
        rationale=oc_decision.rationale or "",
        confidence=oc_decision.confidence,
        alternatives=[
            LaneAlternative(lane=_category_for(alt.value), executor=CxrpExecutorName(alt.value))
            for alt in oc_decision.alternatives_considered
        ],
        execution_target=envelope,
    )


def serialize_cxrp_lane_decision(cxrp: CxrpLaneDecision) -> dict[str, Any]:
    """Render an CxRP ``LaneDecision`` into a JSON-shaped dict.

    Mirrors ``BaseContract.to_dict()`` but recursively unwraps nested
    dataclasses (``LaneAlternative``) and Enum values so the output is
    suitable for direct return from a FastAPI route handler.
    """
    payload = cxrp.to_dict()
    payload["lane"] = (
        payload["lane"].value if hasattr(payload["lane"], "value") else payload["lane"]
    )
    payload["alternatives"] = [asdict(alt) for alt in cxrp.alternatives]
    for alt in payload["alternatives"]:
        alt["lane"] = (
            alt["lane"].value if hasattr(alt["lane"], "value") else alt["lane"]
        )
    return payload
