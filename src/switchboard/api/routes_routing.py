"""Canonical routing endpoints for selector-only SwitchBoard."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Header, Request

from control_plane.contracts import LaneDecision, TaskProposal
from switchboard.domain.decision_record import DecisionRecord
from switchboard.lane.routing import RoutingPlan

router = APIRouter(tags=["routing"])


@router.post("/route", summary="Select a lane for a canonical task proposal")
async def route_task(
    proposal: TaskProposal,
    request: Request,
    x_request_id: str | None = Header(default=None),
) -> LaneDecision:
    selector = request.app.state.selector
    decision = selector.select(proposal)
    _record_decision(request, proposal, decision, x_request_id=x_request_id)
    return decision


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
            selected_profile=decision.selected_lane.value,
            downstream_model=decision.selected_backend.value,
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
            original_model_hint=proposal.task_type.value,
            profile_name=decision.selected_lane.value,
            tenant_id=proposal.project_id,
        )
    )
