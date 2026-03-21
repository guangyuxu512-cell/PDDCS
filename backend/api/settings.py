from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.response import ok
from backend.ai.llm_client import LlmClient
from backend.services.notifier import send_notification
from backend.services.settings_service import get_settings, save_settings


router = APIRouter(tags=["settings"])


class TestLlmBody(BaseModel):
    apiBaseUrl: str
    apiKey: str
    model: str


class TestWebhookBody(BaseModel):
    url: str
    webhookType: str = "feishu"


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


@router.post("/settings/test-webhook")
async def api_test_webhook(body: TestWebhookBody) -> dict[str, Any]:
    sent = await send_notification(
        "PDDCS 通知测试",
        "这是一条来自系统设置页的测试通知。",
        level="info",
        url=body.url,
        webhook_type=body.webhookType,
        dedupe=False,
    )
    if sent:
        return ok({"ok": True, "message": "发送成功"})
    return ok({"ok": False, "message": "发送失败，请检查 Webhook URL 或网络状态"})
