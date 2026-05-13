# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
# ruff: noqa: S101
"""Unit tests for contracts/common.py value objects."""
from __future__ import annotations

import pytest

from switchboard.contracts.common import (
    BranchPolicy,
    ExecutionConstraints,
    TaskTarget,
    ValidationProfile,
)


class TestTaskTarget:
    def test_construction(self) -> None:
        t = TaskTarget(repo_key="my-repo", clone_url="https://github.com/org/repo.git", base_branch="main")
        assert t.repo_key == "my-repo"
        assert t.allowed_paths == []

    def test_frozen(self) -> None:
        t = TaskTarget(repo_key="r", clone_url="u", base_branch="main")
        with pytest.raises(Exception):
            t.repo_key = "changed"  # type: ignore[misc]

    def test_allowed_paths(self) -> None:
        t = TaskTarget(repo_key="r", clone_url="u", base_branch="main", allowed_paths=["src/"])
        assert "src/" in t.allowed_paths


class TestExecutionConstraints:
    def test_defaults(self) -> None:
        ec = ExecutionConstraints()
        assert ec.max_changed_files is None
        assert ec.timeout_seconds == 300
        assert ec.require_clean_validation is True
        assert ec.skip_baseline_validation is False

    def test_custom_values(self) -> None:
        ec = ExecutionConstraints(max_changed_files=10, timeout_seconds=60)
        assert ec.max_changed_files == 10

    def test_frozen(self) -> None:
        ec = ExecutionConstraints()
        with pytest.raises(Exception):
            ec.timeout_seconds = 999  # type: ignore[misc]

    def test_timeout_minimum(self) -> None:
        with pytest.raises(Exception):
            ExecutionConstraints(timeout_seconds=0)


class TestValidationProfile:
    def test_defaults(self) -> None:
        vp = ValidationProfile(profile_name="default")
        assert vp.commands == []
        assert vp.fail_fast is False

    def test_custom(self) -> None:
        vp = ValidationProfile(profile_name="strict", commands=["ruff check ."], fail_fast=True)
        assert vp.fail_fast is True

    def test_frozen(self) -> None:
        vp = ValidationProfile(profile_name="x")
        with pytest.raises(Exception):
            vp.profile_name = "y"  # type: ignore[misc]


class TestBranchPolicy:
    def test_defaults(self) -> None:
        bp = BranchPolicy()
        assert bp.branch_prefix == "auto/"
        assert bp.push_on_success is True
        assert bp.open_pr is False

    def test_custom(self) -> None:
        bp = BranchPolicy(branch_prefix="fix/", open_pr=True)
        assert bp.open_pr is True

    def test_frozen(self) -> None:
        bp = BranchPolicy()
        with pytest.raises(Exception):
            bp.open_pr = True  # type: ignore[misc]
