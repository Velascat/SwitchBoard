"""Model listing endpoint — returns profiles as an OpenAI-style model list.

GET /v1/models
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(tags=["models"])


class ModelObject(BaseModel):
    id: str
    object: str = "model"
    created: int
    owned_by: str = "switchboard"


class ModelListResponse(BaseModel):
    object: str = "list"
    data: list[ModelObject]


@router.get("/v1/models", response_model=ModelListResponse, summary="List available model profiles")
async def list_models(request: Request) -> ModelListResponse:
    """Return all named profiles as OpenAI-compatible model objects.

    Each profile name becomes a model ``id`` that clients can pass in
    ``model`` field of a chat completion request.  SwitchBoard will then
    route based on policy, potentially overriding the requested profile,
    but advertising the profiles lets clients discover what names are valid.
    """
    profile_store = request.app.state.profile_store
    profiles: dict = profile_store.get_profiles()

    created_ts = int(time.time())
    data = [
        ModelObject(id=name, created=created_ts)
        for name in sorted(profiles.keys())
    ]

    return ModelListResponse(data=data)
