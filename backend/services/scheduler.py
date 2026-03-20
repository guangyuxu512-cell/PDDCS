"""店铺级协程调度器。"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable
from typing import Any, TypeVar

from playwright.async_api import Page

from backend.adapters import BaseAdapter, PddAdapter
from backend.ai.llm_client import LlmClient, create_llm_client_from_settings
from backend.db.database import get_db
from backend.engines.human_simulator import HumanSimulator
from backend.engines.playwright_engine import engine
from backend.services.message_processor import process_buyer_message
from backend.services.settings_service import get_settings
from backend.services.shop_service import get_shop_config


logger = logging.getLogger(__name__)

DEFAULT_POLL_INTERVAL_SECONDS = 3.0
DEFAULT_OPERATION_TIMEOUT_SECONDS = 15.0
DEFAULT_ENGINE_TIMEOUT_SECONDS = 70.0
DEFAULT_NAVIGATION_TIMEOUT_SECONDS = 40.0
DEFAULT_LOGIN_TIMEOUT_SECONDS = 130.0
DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS = 50.0
T = TypeVar("T")


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float env %s=%r, using default %s", name, value, default)
        return default


async def _wait(awaitable: Awaitable[T], timeout_seconds: float) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _get_shop_platform(shop_id: str) -> str | None:
    with get_db() as conn:
        row = conn.execute("SELECT platform FROM shops WHERE id=?", (shop_id,)).fetchone()
    if row is None:
        return None
    return str(row["platform"])


def _load_runtime_configuration(shop_id: str) -> tuple[dict[str, Any], LlmClient]:
    settings = get_settings().model_dump(by_alias=False)
    config_model = get_shop_config(shop_id)
    config = config_model.model_dump(by_alias=False) if config_model is not None else {}
    return config, create_llm_client_from_settings(settings=settings, shop_config=config)


def _get_shop_proxy(shop_id: str) -> str:
    config_model = get_shop_config(shop_id)
    if config_model is None:
        return ""
    config = config_model.model_dump(by_alias=False)
    return str(config.get("proxy", "")).strip()


def _update_escalation_log(session_id: str, shop_id: str, success: bool) -> None:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT id
            FROM escalation_logs
            WHERE session_id=? AND shop_id=?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (session_id, shop_id),
        ).fetchone()
        if row is None:
            return
        conn.execute("UPDATE escalation_logs SET success=? WHERE id=?", (int(success), row["id"]))


class ShopScheduler:
    """管理店铺消息轮询任务。"""

    def __init__(self) -> None:
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._engine_lock: asyncio.Lock | None = None

    def _get_engine_lock(self) -> asyncio.Lock:
        if self._engine_lock is None:
            self._engine_lock = asyncio.Lock()
        return self._engine_lock

    async def _ensure_engine_started(self) -> None:
        if engine.is_running:
            return

        async with self._get_engine_lock():
            if engine.is_running:
                return
            await _wait(engine.start(), timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS)

    def _create_adapter(self, platform: str, page: Page, shop_id: str) -> BaseAdapter:
        if platform == "pdd":
            return PddAdapter(page, shop_id, HumanSimulator(page))
        raise ValueError(f"Platform '{platform}' adapter not implemented yet")

    def _on_task_done(self, shop_id: str, task: asyncio.Task[None]) -> None:
        current = self._running_tasks.get(shop_id)
        if current is task:
            self._running_tasks.pop(shop_id, None)

        try:
            task.result()
        except asyncio.CancelledError:
            logger.info("[%s] Shop task cancelled", shop_id)
        except Exception:
            logger.exception("[%s] Shop task crashed", shop_id)

    async def _shop_loop(self, shop_id: str) -> None:
        logger.info("[%s] Shop loop started", shop_id)
        try:
            await self._ensure_engine_started()
            platform = _get_shop_platform(shop_id)
            if platform is None:
                logger.error("[%s] Shop not found", shop_id)
                return

            page = await _wait(
                engine.open_shop(shop_id, proxy=_get_shop_proxy(shop_id)),
                timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS,
            )
            adapter = self._create_adapter(platform, page, shop_id)
            await _wait(adapter.navigate_to_chat(), timeout_seconds=DEFAULT_NAVIGATION_TIMEOUT_SECONDS)

            if hasattr(adapter, "is_logged_in"):
                logged_in = await _wait(adapter.is_logged_in(), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
                if not logged_in and hasattr(adapter, "wait_for_login"):
                    success = await _wait(
                        adapter.wait_for_login(timeout_ms=120000),
                        timeout_seconds=DEFAULT_LOGIN_TIMEOUT_SECONDS,
                    )
                    if not success:
                        logger.error("[%s] Login timeout, stopping loop", shop_id)
                        return

            poll_interval = _env_float("SHOP_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)
            while True:
                try:
                    shop_config, llm_client = _load_runtime_configuration(shop_id)
                    sessions = await _wait(
                        adapter.get_session_list(),
                        timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                    )
                    for session_info in sessions:
                        try:
                            await _wait(
                                adapter.switch_to_session(session_info.session_id),
                                timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                            )
                            raw_messages = await _wait(
                                adapter.fetch_messages(session_info.session_id),
                                timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                            )
                            for message in raw_messages:
                                if message.sender != "buyer":
                                    continue

                                result = await _wait(
                                    process_buyer_message(
                                        shop_id=shop_id,
                                        raw_msg=message,
                                        llm_client=llm_client,
                                    ),
                                    timeout_seconds=_env_float(
                                        "SHOP_MESSAGE_PROCESS_TIMEOUT_SECONDS",
                                        DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS,
                                    ),
                                )
                                if result.action == "skip":
                                    continue

                                if result.action == "reply":
                                    sent = await _wait(
                                        adapter.send_message(session_info.session_id, result.reply_text),
                                        timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                    )
                                    if sent:
                                        logger.info(
                                            "[%s] Replied to %s: %s",
                                            shop_id,
                                            session_info.buyer_name,
                                            result.reply_text[:50],
                                        )
                                    else:
                                        logger.warning(
                                            "[%s] Failed to send reply to %s",
                                            shop_id,
                                            session_info.buyer_name,
                                        )

                                elif result.action == "escalate":
                                    fallback_message = str(shop_config.get("escalation_fallback_msg", "")).strip()
                                    if fallback_message:
                                        await _wait(
                                            adapter.send_message(session_info.session_id, fallback_message),
                                            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                        )

                                    target_agent = str(shop_config.get("human_agent_name", "")).strip()
                                    escalation_success = False
                                    if target_agent:
                                        escalation_success = await _wait(
                                            adapter.trigger_escalation(session_info.session_id, target_agent),
                                            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                        )
                                    _update_escalation_log(result.session_id, shop_id, escalation_success)
                                    logger.info(
                                        "[%s] Escalated %s to %s: %s",
                                        shop_id,
                                        session_info.buyer_name,
                                        target_agent or "未配置客服",
                                        "success" if escalation_success else "failed",
                                    )
                        except Exception:
                            logger.exception(
                                "[%s] Error processing session %s",
                                shop_id,
                                session_info.session_id,
                            )
                            continue
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("[%s] Error in poll cycle", shop_id)

                await _wait(asyncio.sleep(poll_interval), timeout_seconds=poll_interval + 1.0)
        except asyncio.CancelledError:
            logger.info("[%s] Shop loop cancelled", shop_id)
            raise
        except Exception:
            logger.exception("[%s] Shop loop crashed", shop_id)
        finally:
            try:
                await _wait(engine.close_shop(shop_id), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
            except Exception:
                logger.exception("[%s] Failed to close browser context", shop_id)
            logger.info("[%s] Shop loop stopped", shop_id)

    def get_running_shops(self) -> list[str]:
        return [shop_id for shop_id, task in self._running_tasks.items() if not task.done()]

    async def start_shop(self, shop_id: str) -> bool:
        if shop_id in self._running_tasks and not self._running_tasks[shop_id].done():
            logger.warning("[%s] Already running", shop_id)
            return False
        if _get_shop_platform(shop_id) is None:
            logger.warning("[%s] Shop does not exist", shop_id)
            return False

        task = asyncio.create_task(self._shop_loop(shop_id), name=f"shop-{shop_id}")
        self._running_tasks[shop_id] = task
        task.add_done_callback(
            lambda current_task, current_shop_id=shop_id: self._on_task_done(current_shop_id, current_task)
        )
        return True

    async def stop_shop(self, shop_id: str) -> bool:
        task = self._running_tasks.pop(shop_id, None)
        if task is None:
            return False

        task.cancel()
        try:
            await _wait(task, timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            pass

        if not self.get_running_shops() and engine.is_running:
            try:
                await _wait(engine.stop(), timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS)
            except Exception:
                logger.exception("Failed to stop engine after stopping shop %s", shop_id)

        return True

    async def start_all_online_shops(self) -> int:
        with get_db() as conn:
            rows = conn.execute("SELECT id FROM shops WHERE is_online=1 AND ai_enabled=1").fetchall()

        count = 0
        for row in rows:
            if await self.start_shop(str(row["id"])):
                count += 1
        return count

    async def stop_all_shops(self) -> int:
        shop_ids = list(self._running_tasks.keys())
        count = 0
        for shop_id in shop_ids:
            if await self.stop_shop(shop_id):
                count += 1
        return count


_DEFAULT_SCHEDULER = ShopScheduler()


async def start_shop(shop_id: str) -> bool:
    return await _DEFAULT_SCHEDULER.start_shop(shop_id)


async def stop_shop(shop_id: str) -> bool:
    return await _DEFAULT_SCHEDULER.stop_shop(shop_id)


async def start_all_online_shops() -> int:
    return await _DEFAULT_SCHEDULER.start_all_online_shops()


async def stop_all_shops() -> int:
    return await _DEFAULT_SCHEDULER.stop_all_shops()


def get_running_shops() -> list[str]:
    return _DEFAULT_SCHEDULER.get_running_shops()
