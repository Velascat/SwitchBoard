# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Velascat
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from switchboard.app import create_app
from switchboard.config import load_settings


def _proposal() -> dict:
    return {
        "task_id": "route-1",
        "project_id": "switchboard-test",
        "task_type": "documentation",
        "execution_mode": "goal",
        "goal_text": "Refresh the architecture summary",
        "target": {
            "repo_key": "docs",
            "clone_url": "https://example.invalid/docs.git",
            "base_branch": "main",
            "allowed_paths": [],
        },
        "priority": "normal",
        "risk_level": "low",
        "constraints": {
            "allowed_paths": [],
            "require_clean_validation": True,
        },
        "validation_profile": {
            "profile_name": "default",
            "commands": [],
        },
        "branch_policy": {
            "push_on_success": True,
            "open_pr": False,
        },
        "labels": [],
    }


def test_route_persists_canonical_lane_backend_evidence(tmp_path, monkeypatch) -> None:
    decision_log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("SWITCHBOARD_DECISION_LOG_PATH", str(decision_log))
    load_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.post("/route", json=_proposal(), headers={"X-Request-ID": "req-1"})

    assert response.status_code == 200

    entries = [json.loads(line) for line in decision_log.read_text(encoding="utf-8").splitlines()]
    assert len(entries) == 1
    record = entries[0]
    assert record["selected_lane"] == "aider_local"
    assert record["selected_backend"] == "direct_local"
    assert record["request_id"] == "req-1"
    assert "original_model_hint" not in record
    assert "selected_profile" not in record
    assert "downstream_model" not in record
    load_settings.cache_clear()


def test_wire_response_and_audit_log_agree_on_lane_backend(tmp_path, monkeypatch) -> None:
    """Defense against mapper drift: the CxRP envelope returned on the
    wire and the JSONL audit-log entry must name the same executor and
    backend, even though they use different field names internally
    (response.executor / response.backend vs. record.selected_lane /
    record.selected_backend)."""
    decision_log = tmp_path / "decisions.jsonl"
    monkeypatch.setenv("SWITCHBOARD_DECISION_LOG_PATH", str(decision_log))
    load_settings.cache_clear()

    with TestClient(create_app()) as client:
        response = client.post("/route", json=_proposal(), headers={"X-Request-ID": "req-2"})

    assert response.status_code == 200
    wire = response.json()
    assert wire["contract_kind"] == "lane_decision"
    assert wire["schema_version"].startswith("0.")

    entries = [json.loads(line) for line in decision_log.read_text(encoding="utf-8").splitlines()]
    assert entries, "decision logger must persist at least one record"
    record = entries[-1]

    assert wire["executor"] == record["selected_lane"], (
        f"wire executor ({wire['executor']!r}) and audit-log selected_lane "
        f"({record['selected_lane']!r}) disagree — mapper drift?"
    )
    assert wire["backend"] == record["selected_backend"], (
        f"wire backend ({wire['backend']!r}) and audit-log selected_backend "
        f"({record['selected_backend']!r}) disagree — mapper drift?"
    )
    assert wire["proposal_id"] == record["context_summary"]["proposal_id"]
    load_settings.cache_clear()
