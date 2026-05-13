# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
"""TaskProposal — the routing input SwitchBoard receives from OperationsCenter.

SwitchBoard owns this type; it must not import TaskProposal from OC.
The wire shape (JSON field names) is kept in sync with OC's TaskProposal
by convention — a mismatch surfaces as an integration test failure.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .common import BranchPolicy, ExecutionConstraints, TaskTarget, ValidationProfile
from .enums import ExecutionMode, Priority, RiskLevel, TaskType


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class TaskProposal(BaseModel):
    proposal_id: str = Field(default_factory=_new_id)
    task_id: str = Field(description="Upstream task identifier")
    project_id: str = Field(description="Project or board the task belongs to")

    task_type: TaskType = Field(description="Broad category of the proposed work")
    execution_mode: ExecutionMode = Field(description="Execution strategy for the run")
    goal_text: str = Field(description="Natural-language description of what to accomplish")
    constraints_text: str | None = Field(default=None)

    target: TaskTarget = Field(description="Repository and branch context")

    priority: Priority = Field(default=Priority.NORMAL)
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)
    validation_profile: ValidationProfile = Field(
        default_factory=lambda: ValidationProfile(profile_name="default"),
    )
    branch_policy: BranchPolicy = Field(default_factory=BranchPolicy)

    proposed_at: datetime = Field(default_factory=_utcnow)
    proposer: str | None = Field(default=None)
    labels: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}
