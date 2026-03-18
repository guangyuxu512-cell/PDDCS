from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.response import ok
from backend.services.settings_service import get_settings, save_settings, test_llm_connection


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
    return ok(test_llm_connection(body.apiBaseUrl, body.apiKey, body.model))
