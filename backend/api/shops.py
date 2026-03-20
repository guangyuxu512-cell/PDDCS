from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from typing_extensions import Literal

from backend.api.response import fail, ok
from backend.db.database import get_db
from backend.engines.playwright_engine import engine
from backend.services.scheduler import get_running_shops, start_shop, stop_shop
from backend.services.shop_service import (
    create_shop,
    delete_shop,
    get_shop_config,
    list_shops,
    scan_desktop_windows,
    toggle_ai,
    toggle_status,
    update_shop_config,
)


router = APIRouter(tags=["shops"])
logger = logging.getLogger(__name__)


class ToggleAiBody(BaseModel):
    enabled: bool


class CreateShopBody(BaseModel):
    name: str = Field(min_length=1)
    platform: Literal["pdd"]
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _set_shop_online_status(shop_id: str, is_online: bool) -> bool:
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE shops SET is_online=?, updated_at=? WHERE id=?",
            (int(is_online), datetime.now().isoformat(), shop_id),
        )
    return cursor.rowcount > 0


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

    try:
        if shop.is_online:
            await start_shop(shop_id)
        else:
            await stop_shop(shop_id)
    except Exception:
        logger.exception("Toggle scheduler sync failed for %s", shop_id)

    return ok(shop.model_dump())


@router.delete("/shops/{shop_id}")
async def api_delete_shop(shop_id: str) -> dict[str, Any]:
    if not delete_shop(shop_id):
        return fail("店铺不存在")
    return ok(None)


@router.post("/shops/{shop_id}/open-browser")
async def api_open_browser(shop_id: str) -> dict[str, Any]:
    if not _set_shop_online_status(shop_id, True):
        return fail("店铺不存在")

    started = await start_shop(shop_id)
    if not started:
        if shop_id in get_running_shops():
            return ok(None)
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
    if not _set_shop_online_status(shop_id, True):
        return fail("店铺不存在")

    started = await start_shop(shop_id)
    if not started:
        return fail("店铺已在运行中")
    return ok(None)


@router.post("/shops/{shop_id}/stop")
async def api_stop_shop(shop_id: str) -> dict[str, Any]:
    stopped = await stop_shop(shop_id)
    if not stopped:
        return fail("店铺未在运行")

    _set_shop_online_status(shop_id, False)
    return ok(None)


@router.get("/shops/running")
async def api_running_shops() -> dict[str, Any]:
    return ok(get_running_shops())


@router.get("/shops/memory")
async def api_memory_info() -> dict[str, Any]:
    """获取浏览器引擎内存使用信息。"""
    info = await engine.get_memory_info()
    return ok(info)


@router.post("/shops/start-all")
async def api_start_all() -> dict[str, Any]:
    """启动所有已启用的店铺。"""
    from backend.services.scheduler import start_all_online_shops

    count = await start_all_online_shops()
    return ok({"started": count})


@router.post("/shops/stop-all")
async def api_stop_all() -> dict[str, Any]:
    """停止所有运行中的店铺。"""
    from backend.services.scheduler import stop_all_shops

    count = await stop_all_shops()
    return ok({"stopped": count})
