from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from backend.api.response import fail, ok
from backend.services.shop_service import (
    get_shop_config,
    list_shops,
    open_browser,
    toggle_ai,
    toggle_status,
    update_shop_config,
)


router = APIRouter(tags=["shops"])


class ToggleAiBody(BaseModel):
    enabled: bool


@router.get("/shops")
async def api_list_shops() -> dict[str, Any]:
    shops = list_shops()
    return ok([shop.model_dump() for shop in shops])


@router.patch("/shops/{shop_id}/ai")
async def api_toggle_ai(shop_id: str, body: ToggleAiBody) -> dict[str, Any]:
    shop = toggle_ai(shop_id, body.enabled)
    if shop is None:
        return fail("店铺不存在")
    return ok(shop.model_dump())


@router.post("/shops/{shop_id}/toggle")
async def api_toggle_status(shop_id: str) -> dict[str, Any]:
    shop = toggle_status(shop_id)
    if shop is None:
        return fail("店铺不存在")
    return ok(shop.model_dump())


@router.post("/shops/{shop_id}/open-browser")
async def api_open_browser(shop_id: str) -> dict[str, Any]:
    if not open_browser(shop_id):
        return fail("打开浏览器失败")
    return ok(None)


@router.get("/shops/{shop_id}/config")
async def api_get_config(shop_id: str) -> dict[str, Any]:
    config = get_shop_config(shop_id)
    if config is None:
        return fail("店铺不存在")
    return ok(config.model_dump())


@router.put("/shops/{shop_id}/config")
async def api_save_config(shop_id: str, body: dict[str, Any]) -> dict[str, Any]:
    config = update_shop_config(shop_id, body)
    if config is None:
        return fail("保存失败")
    return ok(config.model_dump())
