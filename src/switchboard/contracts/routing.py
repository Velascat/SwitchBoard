# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
"""LaneDecision — SwitchBoard's routing output.

SwitchBoard owns this type; it must not import LaneDecision from OC.
The cxrp_mapper translates this into the CxRP envelope at the API boundary.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, Field

from .enums import BackendName, LaneName


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


class LaneDecision(BaseModel):
    decision_id: str = Field(default_factory=_new_id)
    proposal_id: str = Field(description="ID of the TaskProposal this decision routes")

    selected_lane: LaneName = Field(description="Execution lane chosen for this task")
    selected_backend: BackendName = Field(description="Backend within the lane")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    policy_rule_matched: str | None = Field(default=None)
    rationale: str | None = Field(default=None)
    alternatives_considered: list[LaneName] = Field(default_factory=list)

    decided_at: datetime = Field(default_factory=_utcnow)
    switchboard_version: str | None = Field(default=None)

    model_config = {"frozen": True}
