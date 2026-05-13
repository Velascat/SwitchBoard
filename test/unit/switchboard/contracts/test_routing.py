# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 ProtocolWarden
# ruff: noqa: S101
"""Unit tests for contracts/routing.py."""
from __future__ import annotations

import pytest

from switchboard.contracts.enums import BackendName, LaneName
from switchboard.contracts.routing import LaneDecision


def _minimal(**kwargs) -> LaneDecision:
    defaults = dict(
        proposal_id="prop-1",
        selected_lane=LaneName.CLAUDE_CLI,
        selected_backend=BackendName.ARCHON,
    )
    defaults.update(kwargs)
    return LaneDecision(**defaults)


def test_auto_id_and_timestamp() -> None:
    d = _minimal()
    assert d.decision_id
    assert d.decided_at is not None


def test_unique_ids() -> None:
    assert _minimal().decision_id != _minimal().decision_id


def test_defaults() -> None:
    d = _minimal()
    assert d.confidence == 1.0
    assert d.rationale is None
    assert d.alternatives_considered == []


def test_confidence_bounds() -> None:
    assert _minimal(confidence=0.75).confidence == 0.75
    with pytest.raises(Exception):
        _minimal(confidence=1.1)
    with pytest.raises(Exception):
        _minimal(confidence=-0.1)


def test_frozen() -> None:
    d = _minimal()
    with pytest.raises(Exception):
        d.confidence = 0.5  # type: ignore[misc]


def test_with_rationale_and_alternatives() -> None:
    d = _minimal(
        rationale="Matched high-complexity rule.",
        policy_rule_matched="high_complexity",
        alternatives_considered=[LaneName.AIDER_LOCAL],
    )
    assert d.policy_rule_matched == "high_complexity"
    assert LaneName.AIDER_LOCAL in d.alternatives_considered
