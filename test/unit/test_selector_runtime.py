from __future__ import annotations

from fastapi.testclient import TestClient

from switchboard.app import create_app


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


def test_default_runtime_has_no_proxy_route() -> None:
    with TestClient(create_app()) as client:
        response = client.post(
            "/v1/chat/completions",
            json={"model": "fast", "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 404


def test_route_returns_lane_decision() -> None:
    with TestClient(create_app()) as client:
        response = client.post("/route", json=_proposal())
    assert response.status_code == 200
    data = response.json()
    assert data["selected_lane"] == "aider_local"
    assert data["selected_backend"] == "kodo"


def test_health_has_no_nine_router_dependency() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "nine_router" not in data
    assert data["selector_ready"] is True
