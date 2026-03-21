"""店铺级协程调度器。"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable
from datetime import datetime
from typing import Any, TypeVar

from playwright.async_api import Page

from backend.adapters import BaseAdapter, PddAdapter, SessionInfo
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
DEFAULT_NAVIGATION_TIMEOUT_SECONDS = 180.0
DEFAULT_LOGIN_TIMEOUT_SECONDS = 130.0
DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS = 50.0
DEFAULT_LOGIN_CHECK_INTERVAL = 30
DEFAULT_COOKIE_SAVE_INTERVAL = 1800.0
DEFAULT_MEMORY_CLEANUP_INTERVAL = 3600.0
DEFAULT_CRASH_RECOVERY_MAX_RETRIES = 3
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


async def _sleep(seconds: float) -> None:
    await _wait(asyncio.sleep(seconds), timeout_seconds=seconds + 1.0)


async def _is_shop_context_alive(shop_id: str) -> bool:
    checker = getattr(engine, "is_context_alive", None)
    if not callable(checker):
        return True
    return bool(await _wait(checker(shop_id), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS))


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


def _get_shop_credentials(shop_id: str) -> tuple[str, str]:
    """从 DB 获取店铺账号密码明文。"""
    with get_db() as conn:
        row = conn.execute("SELECT username, password FROM shops WHERE id=?", (shop_id,)).fetchone()
    if row is None:
        return "", ""
    return str(row["username"] or "").strip(), str(row["password"] or "")


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


def _update_shop_status(shop_id: str, **kwargs: Any) -> None:
    """更新店铺状态字段到 DB。"""
    if not kwargs:
        return

    allowed_fields = {"is_online", "cookie_valid", "last_active_at", "today_served_count"}
    sets: list[str] = []
    params: list[Any] = []
    for key, value in kwargs.items():
        if key not in allowed_fields:
            continue
        sets.append(f"{key}=?")
        params.append(int(value) if isinstance(value, bool) else value)

    if not sets:
        return

    sets.append("updated_at=?")
    params.append(datetime.now().isoformat())
    params.append(shop_id)

    with get_db() as conn:
        conn.execute(f"UPDATE shops SET {', '.join(sets)} WHERE id=?", params)


def _get_shop_context(shop_id: str) -> Any | None:
    contexts = getattr(engine, "_contexts", None)
    if not isinstance(contexts, dict):
        return None
    return contexts.get(shop_id)


async def _save_shop_cookies(shop_id: str) -> None:
    context = _get_shop_context(shop_id)
    cookie_manager = getattr(engine, "_cookie_manager", None)
    if context is None or cookie_manager is None:
        return
    await _wait(cookie_manager.save(shop_id, context), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)


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

        try:
            _update_shop_status(shop_id, is_online=False)
            logger.info("[%s] DB status set to offline after task completion", shop_id)
        except Exception:
            logger.exception("[%s] Failed to update DB status in _on_task_done", shop_id)

    async def _is_adapter_logged_in(self, adapter: BaseAdapter) -> bool:
        checker = getattr(adapter, "is_logged_in", None)
        if not callable(checker):
            return True
        return bool(await _wait(checker(), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS))

    async def _wait_for_manual_login(self, shop_id: str, adapter: BaseAdapter) -> bool:
        waiter = getattr(adapter, "wait_for_login", None)
        if not callable(waiter):
            logger.error("[%s] Adapter does not support manual login waiting", shop_id)
            return False
        return bool(await _wait(waiter(timeout_ms=120000), timeout_seconds=DEFAULT_LOGIN_TIMEOUT_SECONDS))

    async def _navigate_adapter_to_chat(self, shop_id: str, adapter: BaseAdapter) -> bool:
        navigate = getattr(adapter, "navigate_to_chat")
        username, password = _get_shop_credentials(shop_id)

        try:
            parameters = inspect.signature(navigate).parameters
        except (TypeError, ValueError):
            parameters = {}

        supports_credentials = "username" in parameters and "password" in parameters
        if username and password and supports_credentials:
            await _wait(
                navigate(username=username, password=password),
                timeout_seconds=DEFAULT_NAVIGATION_TIMEOUT_SECONDS,
            )
            return True

        await _wait(
            navigate(),
            timeout_seconds=DEFAULT_NAVIGATION_TIMEOUT_SECONDS,
        )
        return False

    async def _process_session(
        self,
        shop_id: str,
        adapter: BaseAdapter,
        session_info: SessionInfo,
        shop_config: dict[str, Any],
        llm_client: LlmClient,
    ) -> None:
        """处理单个会话的消息。"""
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
                    logger.info("[%s] Replied to %s", shop_id, session_info.buyer_name)
                else:
                    logger.warning("[%s] Failed to reply to %s", shop_id, session_info.buyer_name)
                continue

            if result.action == "escalate":
                fallback = str(shop_config.get("escalation_fallback_msg", "")).strip()
                if fallback:
                    await _wait(
                        adapter.send_message(session_info.session_id, fallback),
                        timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                    )

                target = str(shop_config.get("human_agent_name", "")).strip()
                success = False
                if target:
                    success = await _wait(
                        adapter.trigger_escalation(session_info.session_id, target),
                        timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                    )
                _update_escalation_log(result.session_id, shop_id, success)

    async def _shop_loop(self, shop_id: str) -> None:
        logger.info("[%s] Shop loop started", shop_id)
        crash_retries = 0
        try:
            while crash_retries <= DEFAULT_CRASH_RECOVERY_MAX_RETRIES:
                try:
                    await self._ensure_engine_started()
                    platform = _get_shop_platform(shop_id)
                    if platform is None:
                        logger.error("[%s] Shop not found in DB", shop_id)
                        return

                    proxy = _get_shop_proxy(shop_id)
                    page = await _wait(
                        engine.open_shop(shop_id, proxy=proxy),
                        timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS,
                    )
                    adapter = self._create_adapter(platform, page, shop_id)

                    used_credentials = await self._navigate_adapter_to_chat(shop_id, adapter)

                    logged_in = await self._is_adapter_logged_in(adapter)
                    if not logged_in:
                        if used_credentials:
                            logger.error("[%s] Automatic login failed, stopping", shop_id)
                            _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                            return
                        logger.warning("[%s] Not logged in, waiting for manual login...", shop_id)
                        _update_shop_status(shop_id, is_online=True, cookie_valid=False)
                        success = await self._wait_for_manual_login(shop_id, adapter)
                        if not success:
                            logger.error("[%s] Login timeout, stopping", shop_id)
                            _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                            return

                    _update_shop_status(shop_id, is_online=True, cookie_valid=True)
                    try:
                        await _save_shop_cookies(shop_id)
                        logger.info("[%s] Cookie saved after login", shop_id)
                    except Exception:
                        logger.exception("[%s] Failed to save cookie after login", shop_id)

                    crash_retries = 0

                    poll_interval = _env_float("SHOP_POLL_INTERVAL_SECONDS", DEFAULT_POLL_INTERVAL_SECONDS)
                    poll_count = 0
                    loop = asyncio.get_running_loop()
                    last_cookie_save_time = loop.time()
                    last_memory_cleanup_time = loop.time()

                    while True:
                        poll_count += 1
                        now = loop.time()

                        if not await _is_shop_context_alive(shop_id):
                            context_exists = _get_shop_context(shop_id) is not None
                            if not context_exists:
                                logger.warning(
                                    "[%s] Browser context closed externally, stopping gracefully",
                                    shop_id,
                                )
                                _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                                return

                            logger.warning(
                                "[%s] Browser context alive but page is dead, triggering crash recovery",
                                shop_id,
                            )
                            raise RuntimeError("Page dead, need crash recovery")

                        if poll_count % DEFAULT_LOGIN_CHECK_INTERVAL == 0:
                            still_logged_in = await self._is_adapter_logged_in(adapter)
                            if not still_logged_in:
                                logger.warning("[%s] Session expired! Attempting re-login...", shop_id)
                                _update_shop_status(shop_id, cookie_valid=False)
                                used_credentials = await self._navigate_adapter_to_chat(shop_id, adapter)
                                still_logged_in = await self._is_adapter_logged_in(adapter)
                                if not still_logged_in:
                                    if used_credentials:
                                        logger.error("[%s] Automatic re-login failed", shop_id)
                                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                                        return
                                    logger.warning(
                                        "[%s] Still not logged in, waiting for manual login...",
                                        shop_id,
                                    )
                                    success = await self._wait_for_manual_login(shop_id, adapter)
                                    if not success:
                                        logger.error("[%s] Re-login timeout", shop_id)
                                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                                        return

                                _update_shop_status(shop_id, cookie_valid=True)
                                try:
                                    await _save_shop_cookies(shop_id)
                                except Exception:
                                    logger.exception("[%s] Failed to save cookie after re-login", shop_id)

                        if now - last_cookie_save_time >= DEFAULT_COOKIE_SAVE_INTERVAL:
                            try:
                                await _save_shop_cookies(shop_id)
                            except Exception:
                                logger.exception("[%s] Periodic cookie save failed", shop_id)
                            last_cookie_save_time = now

                        if now - last_memory_cleanup_time >= DEFAULT_MEMORY_CLEANUP_INTERVAL:
                            try:
                                await _wait(
                                    engine.cleanup_extra_pages(shop_id),
                                    timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                )
                            except Exception:
                                logger.exception("[%s] Memory cleanup failed", shop_id)
                            last_memory_cleanup_time = now

                        try:
                            if poll_count % 10 == 0:
                                try:
                                    dismiss_fn = getattr(adapter, "dismiss_popups", None)
                                    if callable(dismiss_fn):
                                        await _wait(
                                            dismiss_fn(max_rounds=1),
                                            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                        )
                                except Exception:
                                    logger.debug("[%s] Periodic popup dismiss failed", shop_id)

                            shop_config, llm_client = _load_runtime_configuration(shop_id)
                            sessions = await _wait(
                                adapter.get_session_list(),
                                timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                            )
                            for session_info in sessions:
                                try:
                                    await self._process_session(
                                        shop_id,
                                        adapter,
                                        session_info,
                                        shop_config,
                                        llm_client,
                                    )
                                except asyncio.CancelledError:
                                    raise
                                except Exception:
                                    logger.exception(
                                        "[%s] Error processing session %s",
                                        shop_id,
                                        session_info.session_id,
                                    )
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception("[%s] Error in poll cycle", shop_id)

                        await _sleep(poll_interval)
                except asyncio.CancelledError:
                    raise
                except Exception:
                    crash_retries += 1
                    logger.exception(
                        "[%s] Shop loop crashed (attempt %d/%d), restarting...",
                        shop_id,
                        crash_retries,
                        DEFAULT_CRASH_RECOVERY_MAX_RETRIES,
                    )
                    if crash_retries > DEFAULT_CRASH_RECOVERY_MAX_RETRIES:
                        logger.error("[%s] Max crash retries exceeded, stopping", shop_id)
                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                        return

                    contexts = getattr(engine, "_contexts", None)
                    if isinstance(contexts, dict) and shop_id not in contexts:
                        logger.warning(
                            "[%s] Browser context gone during crash recovery, stopping gracefully",
                            shop_id,
                        )
                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                        return

                    try:
                        proxy = _get_shop_proxy(shop_id)
                        await _wait(
                            engine.restart_shop(shop_id, proxy=proxy),
                            timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS,
                        )
                    except Exception:
                        logger.exception("[%s] Restart failed", shop_id)
                    await _sleep(5.0)
        except asyncio.CancelledError:
            logger.info("[%s] Shop loop cancelled", shop_id)
            raise
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
            try:
                await _wait(engine.close_shop(shop_id), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
            except Exception:
                logger.debug("[%s] No browser context to clean up while stopping", shop_id)
            return False

        task.cancel()
        try:
            await _wait(task, timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            pass
        except (asyncio.TimeoutError, TimeoutError):
            logger.warning("[%s] Task cancel timed out, force-closing browser context", shop_id)
            try:
                await _wait(engine.close_shop(shop_id), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
            except Exception:
                logger.exception("[%s] Force close_shop failed", shop_id)
        except Exception:
            logger.exception("[%s] Task finished with error while stopping", shop_id)

        _update_shop_status(shop_id, is_online=False)

        if not self.get_running_shops() and engine.is_running:
            try:
                await _wait(engine.stop(), timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS)
            except Exception:
                logger.exception("Failed to stop engine after stopping shop %s", shop_id)

        return True

    async def start_all_online_shops(self) -> int:
        with get_db() as conn:
            rows = conn.execute("SELECT id FROM shops WHERE is_online=1 AND ai_enabled=1").fetchall()

        tasks: list[Awaitable[bool]] = []
        for row in rows:
            shop_id = str(row["id"])
            if shop_id not in self._running_tasks or self._running_tasks[shop_id].done():
                tasks.append(self.start_shop(shop_id))

        if not tasks:
            return 0

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error("Failed to start shop: %s", result)
        return sum(1 for result in results if result is True)

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
