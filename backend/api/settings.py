from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.response import ok
from backend.ai.llm_client import LlmClient
from backend.services.settings_service import get_settings, save_settings


router = APIRouter(tags=["settings"])


class TestLlmBody(BaseModel):
    apiBaseUrl: str
    apiKey: str
    model: str


@router.get("/settings")
async def api_get_settings() -> dict[str, Any]:
    settings = get_settings()
    return ok(settings.model_dump())


@router.put("/settings")
async def api_save_settings(body: dict[str, Any]) -> dict[str, Any]:
    settings = save_settings(body)
    return ok(settings.model_dump())


@router.post("/settings/test-llm")
async def api_test_llm(body: TestLlmBody) -> dict[str, Any]:
    client = LlmClient(
        api_base_url=body.apiBaseUrl,
        api_key=body.apiKey,
        model=body.model,
    )
    return ok(await client.test_connection())
