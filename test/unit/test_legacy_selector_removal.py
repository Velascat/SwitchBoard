from __future__ import annotations

import importlib.util

from fastapi.testclient import TestClient

from switchboard.app import create_app


def test_legacy_selector_modules_are_not_shipped() -> None:
    assert importlib.util.find_spec("switchboard.services.selector") is None
    assert importlib.util.find_spec("switchboard.services.classifier") is None
    assert importlib.util.find_spec("switchboard.domain.selection_context") is None
    assert importlib.util.find_spec("switchboard.api.routes_models") is None


def test_model_listing_endpoint_is_not_exposed() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/v1/models")
    assert response.status_code == 404
