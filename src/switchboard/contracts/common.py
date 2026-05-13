# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
"""Shared value objects embedded in SwitchBoard's TaskProposal."""
from __future__ import annotations

from pydantic import BaseModel, Field


class TaskTarget(BaseModel):
    repo_key: str = Field(description="Logical name for the repository")
    clone_url: str = Field(description="Git clone URL")
    base_branch: str = Field(description="Branch from which the task branch is created")
    allowed_paths: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}


class ExecutionConstraints(BaseModel):
    max_changed_files: int | None = Field(default=None)
    timeout_seconds: int = Field(default=300, ge=1)
    allowed_paths: list[str] = Field(default_factory=list)
    require_clean_validation: bool = Field(default=True)
    skip_baseline_validation: bool = Field(default=False)

    model_config = {"frozen": True}


class ValidationProfile(BaseModel):
    profile_name: str = Field(description="Logical name, e.g. 'strict', 'lint_only', 'off'")
    commands: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=300, ge=1)
    fail_fast: bool = Field(default=False)

    model_config = {"frozen": True}


class BranchPolicy(BaseModel):
    branch_prefix: str = Field(default="auto/")
    push_on_success: bool = Field(default=True)
    open_pr: bool = Field(default=False)
    allowed_base_branches: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}
