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
