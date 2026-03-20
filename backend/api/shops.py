from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing_extensions import Literal

from backend.api.response import fail, ok
from backend.services.scheduler import get_running_shops, start_shop, stop_shop
from backend.services.shop_service import (
    create_shop,
    delete_shop,
    get_shop_config,
    list_shops,
    open_browser,
    scan_desktop_windows,
    toggle_ai,
    toggle_status,
    update_shop_config,
)


router = APIRouter(tags=["shops"])


class ToggleAiBody(BaseModel):
    enabled: bool


class CreateShopBody(BaseModel):
    name: str = Field(min_length=1)
    platform: Literal["pdd"]
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


@router.get("/shops")
async def api_list_shops() -> dict[str, Any]:
    shops = list_shops()
    return ok([shop.model_dump() for shop in shops])


@router.post("/shops")
async def api_create_shop(body: CreateShopBody) -> dict[str, Any]:
    shop = create_shop(body.name, body.platform, body.username, body.password)
    return ok(shop.model_dump())


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


@router.delete("/shops/{shop_id}")
async def api_delete_shop(shop_id: str) -> dict[str, Any]:
    if not delete_shop(shop_id):
        return fail("店铺不存在")
    return ok(None)


@router.post("/shops/{shop_id}/open-browser")
async def api_open_browser(shop_id: str) -> dict[str, Any]:
    if not open_browser(shop_id):
        return fail("打开浏览器失败")
    return ok(None)


@router.post("/shops/scan")
async def api_scan_desktop_windows() -> dict[str, Any]:
    # TODO: 后续通过 pywinauto/win32gui 扫描千牛/抖店桌面窗口
    shops = scan_desktop_windows()
    return ok([shop.model_dump() for shop in shops])


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


@router.post("/shops/{shop_id}/start")
async def api_start_shop(shop_id: str) -> dict[str, Any]:
    started = await start_shop(shop_id)
    if not started:
        return fail("店铺已在运行中或不存在")
    return ok(None)


@router.post("/shops/{shop_id}/stop")
async def api_stop_shop(shop_id: str) -> dict[str, Any]:
    stopped = await stop_shop(shop_id)
    if not stopped:
        return fail("店铺未在运行")
    return ok(None)


@router.get("/shops/running")
async def api_running_shops() -> dict[str, Any]:
    return ok(get_running_shops())
