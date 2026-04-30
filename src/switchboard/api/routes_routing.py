# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
"""Canonical routing endpoints for selector-only SwitchBoard.

The ``/route`` endpoint emits the CxRP v0.2 ``LaneDecision`` envelope on
the wire. SwitchBoard's selector still produces an OC-narrowed
``LaneDecision`` internally (typed enums for policy and audit); the CxRP
mapper translates at the response boundary.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Header, Request
from operations_center.contracts import LaneDecision, TaskProposal

from switchboard.adapters.cxrp_mapper import (
    serialize_cxrp_lane_decision,
    to_cxrp_lane_decision,
)
from switchboard.domain.decision_record import DecisionRecord
from switchboard.lane.routing import RoutingPlan

router = APIRouter(tags=["routing"])


@router.post("/route", summary="Select a lane for a canonical task proposal")
async def route_task(
    proposal: TaskProposal,
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> dict[str, Any]:
    selector = request.app.state.selector
    decision = selector.select(proposal)
    _record_decision(request, proposal, decision, x_request_id=x_request_id)
    return serialize_cxrp_lane_decision(to_cxrp_lane_decision(decision))


@router.post("/route-plan", response_model=RoutingPlan, summary="Return primary, fallback, and escalation routes")
async def route_plan(
    proposal: TaskProposal,
    request: Request,
) -> RoutingPlan:
    planner = request.app.state.planner
    return planner.plan(proposal)


def _record_decision(
    request: Request,
    proposal: TaskProposal,
    decision: LaneDecision,
    *,
    x_request_id: str | None,
) -> None:
    decision_logger = request.app.state.decision_logger
    decision_logger.append(
        DecisionRecord(
            timestamp=datetime.now(UTC).isoformat(),
            client=proposal.project_id,
            task_type=proposal.task_type.value,
            selected_lane=decision.selected_lane.value,
            selected_backend=decision.selected_backend.value,
            rule_name=decision.policy_rule_matched or "fallback",
            reason=decision.rationale or "",
            context_summary={
                "proposal_id": proposal.proposal_id,
                "risk_level": proposal.risk_level.value,
                "execution_mode": proposal.execution_mode.value,
                "priority": proposal.priority.value,
                "labels": list(proposal.labels),
            },
            request_id=x_request_id,
        )
    )
