"""Worker process entrypoint and reusable shop runtime implementation."""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
from collections.abc import Awaitable
from datetime import datetime
from multiprocessing.queues import Queue
from queue import Empty
from typing import Any, TypeVar

from dotenv import load_dotenv
from playwright.async_api import Page
from sqlalchemy import select

from backend.adapters import BaseAdapter, PddAdapter, SessionInfo
from backend.ai.llm_client import LlmClient, create_llm_client_from_settings
from backend.core.crypto import decrypt
from backend.db.database import get_sync_session
from backend.db.orm import EscalationLogTable, ShopTable
from backend.engines.human_simulator import HumanSimulator
from backend.engines.playwright_engine import engine
from backend.services.message_processor import process_buyer_message
from backend.services.notifier import send_notification
from backend.services.settings_service import get_settings
from backend.services.shop_service import get_shop_config
from backend.workers.protocol import (
    Command,
    ShopCrashRecovery,
    ShopLoginFailed,
    ShopOffline,
    ShopOnline,
    Shutdown,
    StartShop,
    StatusEvent,
    StopShop,
    WorkerHeartbeat,
)


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
DEFAULT_WORKER_HEARTBEAT_INTERVAL_SECONDS = 30.0
DEFAULT_COMMAND_POLL_TIMEOUT_SECONDS = 1.0
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
    with get_sync_session() as session:
        row = session.get(ShopTable, shop_id)
    if row is None:
        return None
    return str(row.platform)


def _load_runtime_configuration(shop_id: str) -> tuple[dict[str, Any], LlmClient]:
    settings = get_settings().model_dump(by_alias=False)
    config_model = get_shop_config(shop_id)
    config = config_model.model_dump(by_alias=False) if config_model is not None else {}
    return config, create_llm_client_from_settings(settings=settings, shop_config=config)


def _get_shop_credentials(shop_id: str) -> tuple[str, str]:
    with get_sync_session() as session:
        row = session.get(ShopTable, shop_id)
    if row is None:
        return "", ""

    password = str(row.password or "")
    if row.password_encrypted:
        try:
            password = decrypt(row.password_encrypted)
        except ValueError:
            logger.warning("[%s] Failed to decrypt stored password, falling back to legacy plaintext", shop_id)
    return str(row.username or "").strip(), password


def _get_shop_restart_policy(shop_id: str) -> bool:
    config_model = get_shop_config(shop_id)
    if config_model is None:
        return False
    config = config_model.model_dump(by_alias=False)
    return bool(config.get("auto_restart", False))


def _get_shop_force_online(shop_id: str) -> bool:
    config_model = get_shop_config(shop_id)
    if config_model is None:
        return False
    config = config_model.model_dump(by_alias=False)
    return bool(config.get("force_online", False))


def _get_shop_proxy(shop_id: str) -> str:
    config_model = get_shop_config(shop_id)
    if config_model is None:
        return ""
    config = config_model.model_dump(by_alias=False)
    return str(config.get("proxy", "")).strip()


def _update_escalation_log(session_id: str, shop_id: str, success: bool) -> None:
    with get_sync_session() as session:
        row = session.scalar(
            select(EscalationLogTable)
            .where(
                EscalationLogTable.session_id == session_id,
                EscalationLogTable.shop_id == shop_id,
            )
            .order_by(EscalationLogTable.created_at.desc())
        )
        if row is None:
            return
        row.success = success


def _update_shop_status(shop_id: str, **kwargs: Any) -> None:
    if not kwargs:
        return

    allowed_fields = {"is_online", "cookie_valid", "last_active_at", "today_served_count"}
    with get_sync_session() as session:
        shop = session.get(ShopTable, shop_id)
        if shop is None:
            return

        updated = False
        for key, value in kwargs.items():
            if key not in allowed_fields:
                continue
            setattr(shop, key, value)
            updated = True

        if not updated:
            return

        shop.updated_at = datetime.now().isoformat()


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


def _split_session_buyer_messages(raw_messages: list[RawMessage]) -> tuple[list[RawMessage], RawMessage | None]:
    buyer_indexes = [
        index
        for index, message in enumerate(raw_messages)
        if message.sender == "buyer" and message.content.strip()
    ]
    if not buyer_indexes:
        return [], None

    last_buyer_index = buyer_indexes[-1]
    history_messages = [raw_messages[index] for index in buyer_indexes[:-1]]
    last_buyer_message = raw_messages[last_buyer_index]
    has_human_reply_after = any(message.sender == "human" for message in raw_messages[last_buyer_index + 1 :])

    if has_human_reply_after:
        history_messages.append(last_buyer_message)
        return history_messages, None
    return history_messages, last_buyer_message


class ShopRuntime:
    """Reusable shop runtime that can run in main process or worker process."""

    def __init__(
        self,
        *,
        worker_id: int = 0,
        status_queue: Queue[StatusEvent] | None = None,
    ) -> None:
        self._running_tasks: dict[str, asyncio.Task[None]] = {}
        self._engine_lock: asyncio.Lock | None = None
        self._worker_id = worker_id
        self._status_queue = status_queue
        self._proxy_overrides: dict[str, str] = {}
        self._login_fail_count: dict[str, int] = {}
        self._stop_reasons: dict[str, str] = {}

    def _emit_status(self, event: StatusEvent) -> None:
        if self._status_queue is None:
            return
        try:
            self._status_queue.put_nowait(event)
        except Exception:
            logger.exception("Failed to publish status event %s", event)

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

    def _clear_proxy_override(self, shop_id: str) -> None:
        self._proxy_overrides.pop(shop_id, None)

    def _set_proxy_override(self, shop_id: str, proxy: str) -> None:
        if proxy.strip():
            self._proxy_overrides[shop_id] = proxy.strip()
            return
        self._proxy_overrides.pop(shop_id, None)

    def _resolve_proxy(self, shop_id: str) -> str:
        override = self._proxy_overrides.get(shop_id)
        if override is not None:
            return override
        return _get_shop_proxy(shop_id)

    def _set_stop_reason(self, shop_id: str, reason: str) -> None:
        self._stop_reasons[shop_id] = reason

    def _is_login_failure_reason(self, reason: str) -> bool:
        return reason in {
            "automatic_login_failed",
            "manual_login_timeout",
            "automatic_relogin_failed",
            "manual_relogin_timeout",
        }

    def _on_task_done(self, shop_id: str, task: asyncio.Task[None]) -> None:
        current = self._running_tasks.get(shop_id)
        if current is task:
            self._running_tasks.pop(shop_id, None)
        reason = self._stop_reasons.pop(shop_id, "")

        was_cancelled = False
        try:
            task.result()
        except asyncio.CancelledError:
            was_cancelled = True
            logger.info("[%s] Shop task cancelled", shop_id)
        except Exception:
            logger.exception("[%s] Shop task crashed", shop_id)

        try:
            if not was_cancelled and _get_shop_restart_policy(shop_id):
                if self._is_login_failure_reason(reason):
                    failure_count = self._login_fail_count.get(shop_id, 0) + 1
                    self._login_fail_count[shop_id] = failure_count
                    if failure_count >= 3:
                        self._clear_proxy_override(shop_id)
                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                        self._emit_status(
                            ShopOffline(
                                shop_id=shop_id,
                                worker_id=self._worker_id,
                                reason="login_failures_exceeded",
                            )
                        )
                        logger.error("[%s] Login failed %s times, auto restart paused", shop_id, failure_count)
                        asyncio.create_task(
                            send_notification(
                                "登录多次失败",
                                f"店铺 {shop_id} 连续 {failure_count} 次登录失败，已暂停自动重启，请手动检查",
                                level="error",
                                event_key=f"{shop_id}:login_failures_exceeded",
                            )
                        )
                        return
                else:
                    self._login_fail_count.pop(shop_id, None)

                _update_shop_status(shop_id, is_online=False)
                logger.info("[%s] auto_restart=ON, scheduling restart in 10 seconds", shop_id)
                asyncio.get_event_loop().call_later(
                    10.0,
                    lambda: asyncio.create_task(self._auto_restart_shop(shop_id)),
                )
                return

            if not self._is_login_failure_reason(reason):
                self._login_fail_count.pop(shop_id, None)
            self._clear_proxy_override(shop_id)
            _update_shop_status(shop_id, is_online=False)
            self._emit_status(ShopOffline(shop_id=shop_id, worker_id=self._worker_id, reason="task_done"))
            logger.info("[%s] DB status set to offline after task completion", shop_id)
        except Exception:
            logger.exception("[%s] Failed to update DB status in _on_task_done", shop_id)

    async def _auto_restart_shop(self, shop_id: str) -> None:
        try:
            if not _get_shop_restart_policy(shop_id):
                logger.info("[%s] auto_restart is disabled, skipping scheduled restart", shop_id)
                return

            running_task = self._running_tasks.get(shop_id)
            if running_task is not None and not running_task.done():
                logger.info("[%s] Shop task already running, skipping scheduled restart", shop_id)
                return

            started = await self.start_shop(shop_id)
            if started:
                logger.info("[%s] Scheduled auto restart triggered successfully", shop_id)
            else:
                logger.warning("[%s] Scheduled auto restart did not start a new task", shop_id)
        except Exception:
            logger.exception("[%s] Scheduled auto restart failed", shop_id)

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
        await _wait(
            adapter.switch_to_session(session_info.session_id),
            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
        )
        raw_messages = await _wait(
            adapter.fetch_messages(session_info.session_id),
            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
        )
        history_messages, pending_message = _split_session_buyer_messages(raw_messages)
        process_timeout = _env_float(
            "SHOP_MESSAGE_PROCESS_TIMEOUT_SECONDS",
            DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS,
        )

        for history_message in history_messages:
            await _wait(
                process_buyer_message(
                    shop_id=shop_id,
                    raw_msg=history_message,
                    llm_client=llm_client,
                    ai_enabled=False,
                ),
                timeout_seconds=process_timeout,
            )

        if pending_message is None:
            if history_messages:
                logger.info(
                    "[%s] Skip auto reply for %s because human replied after the latest buyer message",
                    shop_id,
                    session_info.buyer_name,
                )
            return

        result = await _wait(
            process_buyer_message(
                shop_id=shop_id,
                raw_msg=pending_message,
                llm_client=llm_client,
                ai_enabled=bool(shop_config.get("ai_enabled", False)),
            ),
            timeout_seconds=process_timeout,
        )
        if result.action in {"skip", "stored"}:
            return

        if result.action == "reply":
            sent = await _wait(
                adapter.send_message(session_info.session_id, result.reply_text),
                timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
            )
            if sent:
                logger.info("[%s] Replied to %s", shop_id, session_info.buyer_name)
            else:
                logger.warning("[%s] Failed to reply to %s", shop_id, session_info.buyer_name)
            return

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
        logger.info("[%s] Shop loop started in worker %s", shop_id, self._worker_id)
        crash_retries = 0
        try:
            while crash_retries <= DEFAULT_CRASH_RECOVERY_MAX_RETRIES:
                try:
                    await self._ensure_engine_started()
                    platform = _get_shop_platform(shop_id)
                    if platform is None:
                        logger.error("[%s] Shop not found in DB", shop_id)
                        self._emit_status(ShopOffline(shop_id=shop_id, worker_id=self._worker_id, reason="missing_shop"))
                        return

                    proxy = self._resolve_proxy(shop_id)
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
                            self._set_stop_reason(shop_id, "automatic_login_failed")
                            _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                            self._emit_status(ShopLoginFailed(shop_id=shop_id, worker_id=self._worker_id))
                            self._emit_status(
                                ShopOffline(shop_id=shop_id, worker_id=self._worker_id, reason="automatic_login_failed")
                            )
                            await send_notification(
                                "登录失败",
                                f"店铺 {shop_id} 登录失败，可能需要手动处理验证码",
                                level="error",
                                event_key=f"{shop_id}:automatic_login_failed",
                            )
                            return
                        logger.warning("[%s] Not logged in, waiting for manual login...", shop_id)
                        _update_shop_status(shop_id, is_online=True, cookie_valid=False)
                        success = await self._wait_for_manual_login(shop_id, adapter)
                        if not success:
                            logger.error("[%s] Login timeout, stopping", shop_id)
                            self._set_stop_reason(shop_id, "manual_login_timeout")
                            _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                            self._emit_status(ShopLoginFailed(shop_id=shop_id, worker_id=self._worker_id))
                            self._emit_status(
                                ShopOffline(shop_id=shop_id, worker_id=self._worker_id, reason="manual_login_timeout")
                            )
                            return

                    self._login_fail_count.pop(shop_id, None)
                    _update_shop_status(shop_id, is_online=True, cookie_valid=True)
                    self._emit_status(ShopOnline(shop_id=shop_id, worker_id=self._worker_id))
                    try:
                        await _save_shop_cookies(shop_id)
                        logger.info("[%s] Cookie saved after login", shop_id)
                    except Exception:
                        logger.exception("[%s] Failed to save cookie after login", shop_id)

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
                                if _get_shop_restart_policy(shop_id):
                                    logger.warning(
                                        "[%s] Browser closed externally, auto_restart=ON -> restarting",
                                        shop_id,
                                    )
                                    raise RuntimeError("Browser closed externally, auto_restart triggered")

                                logger.warning("[%s] Browser context closed externally, stopping gracefully", shop_id)
                                _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                                self._emit_status(
                                    ShopOffline(
                                        shop_id=shop_id,
                                        worker_id=self._worker_id,
                                        reason="browser_context_closed",
                                    )
                                )
                                return

                            logger.warning("[%s] Browser context alive but page is dead, triggering crash recovery", shop_id)
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
                                        self._set_stop_reason(shop_id, "automatic_relogin_failed")
                                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                                        self._emit_status(ShopLoginFailed(shop_id=shop_id, worker_id=self._worker_id))
                                        self._emit_status(
                                            ShopOffline(
                                                shop_id=shop_id,
                                                worker_id=self._worker_id,
                                                reason="automatic_relogin_failed",
                                            )
                                        )
                                        await send_notification(
                                            "登录失败",
                                            f"店铺 {shop_id} 登录失败，可能需要手动处理验证码",
                                            level="error",
                                            event_key=f"{shop_id}:automatic_relogin_failed",
                                        )
                                        return
                                    logger.warning("[%s] Still not logged in, waiting for manual login...", shop_id)
                                    success = await self._wait_for_manual_login(shop_id, adapter)
                                    if not success:
                                        logger.error("[%s] Re-login timeout", shop_id)
                                        self._set_stop_reason(shop_id, "manual_relogin_timeout")
                                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                                        self._emit_status(ShopLoginFailed(shop_id=shop_id, worker_id=self._worker_id))
                                        self._emit_status(
                                            ShopOffline(
                                                shop_id=shop_id,
                                                worker_id=self._worker_id,
                                                reason="manual_relogin_timeout",
                                            )
                                        )
                                        return

                                self._login_fail_count.pop(shop_id, None)
                                _update_shop_status(shop_id, cookie_valid=True)
                                self._emit_status(ShopOnline(shop_id=shop_id, worker_id=self._worker_id))
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

                        poll_succeeded = False
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

                            if poll_count % 30 == 0 and _get_shop_force_online(shop_id):
                                try:
                                    ensure_fn = getattr(adapter, "ensure_online_status", None)
                                    if callable(ensure_fn):
                                        is_online = await _wait(
                                            ensure_fn(),
                                            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                        )
                                        if not is_online:
                                            logger.warning(
                                                "[%s] force_online: failed to ensure online status",
                                                shop_id,
                                            )
                                except Exception:
                                    logger.debug("[%s] force_online check failed", shop_id)

                            if poll_count % 20 == 0:
                                try:
                                    detect_timeout_fn = getattr(adapter, "detect_session_timeout", None)
                                    if callable(detect_timeout_fn):
                                        timeout_detected = await _wait(
                                            detect_timeout_fn(),
                                            timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                        )
                                        if timeout_detected:
                                            logger.warning("[%s] Session timeout detected, page refreshed", shop_id)
                                            await send_notification(
                                                "页面超时",
                                                f"店铺 {shop_id} 页面超时已自动刷新",
                                                event_key=f"{shop_id}:session_timeout",
                                            )
                                            find_chat_frame = getattr(adapter, "_find_chat_frame", None)
                                            if callable(find_chat_frame):
                                                adapter._chat_frame = await _wait(
                                                    find_chat_frame(),
                                                    timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS,
                                                )
                                except Exception:
                                    logger.debug("[%s] session timeout check failed", shop_id)

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
                            poll_succeeded = True
                        except asyncio.CancelledError:
                            raise
                        except Exception:
                            logger.exception("[%s] Error in poll cycle", shop_id)

                        if poll_succeeded:
                            crash_retries = 0

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
                    self._emit_status(
                        ShopCrashRecovery(
                            shop_id=shop_id,
                            worker_id=self._worker_id,
                            attempt=crash_retries,
                        )
                    )
                    if crash_retries > DEFAULT_CRASH_RECOVERY_MAX_RETRIES:
                        logger.error("[%s] Max crash retries exceeded, stopping", shop_id)
                        _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                        self._emit_status(
                            ShopOffline(shop_id=shop_id, worker_id=self._worker_id, reason="max_crash_retries")
                        )
                        return

                    contexts = getattr(engine, "_contexts", None)
                    if isinstance(contexts, dict) and shop_id not in contexts:
                        if _get_shop_restart_policy(shop_id):
                            logger.warning("[%s] Browser context gone, auto_restart=ON -> will reopen", shop_id)
                        else:
                            logger.warning("[%s] Browser context gone during crash recovery, stopping gracefully", shop_id)
                            _update_shop_status(shop_id, is_online=False, cookie_valid=False)
                            self._emit_status(
                                ShopOffline(
                                    shop_id=shop_id,
                                    worker_id=self._worker_id,
                                    reason="browser_context_missing",
                                )
                            )
                            return

                    try:
                        proxy = self._resolve_proxy(shop_id)
                        logger.info("[%s] Crash recovery: restarting browser...", shop_id)
                        await _wait(
                            engine.restart_shop(shop_id, proxy=proxy),
                            timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS,
                        )
                        logger.info("[%s] Crash recovery: browser restarted OK", shop_id)
                    except Exception:
                        logger.exception("[%s] Restart failed", shop_id)
                    await _sleep(8.0)
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

    async def start_shop(self, shop_id: str, proxy: str = "") -> bool:
        if shop_id in self._running_tasks and not self._running_tasks[shop_id].done():
            logger.warning("[%s] Already running", shop_id)
            return False
        if _get_shop_platform(shop_id) is None:
            logger.warning("[%s] Shop does not exist", shop_id)
            return False

        self._login_fail_count.pop(shop_id, None)
        self._stop_reasons.pop(shop_id, None)
        self._set_proxy_override(shop_id, proxy)
        task = asyncio.create_task(self._shop_loop(shop_id), name=f"shop-{shop_id}")
        self._running_tasks[shop_id] = task
        task.add_done_callback(
            lambda current_task, current_shop_id=shop_id: self._on_task_done(current_shop_id, current_task)
        )
        return True

    async def stop_shop(self, shop_id: str) -> bool:
        task = self._running_tasks.pop(shop_id, None)
        self._clear_proxy_override(shop_id)
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
        self._emit_status(ShopOffline(shop_id=shop_id, worker_id=self._worker_id, reason="stop_command"))

        if not self.get_running_shops() and engine.is_running:
            try:
                await _wait(engine.stop(), timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS)
            except Exception:
                logger.exception("Failed to stop engine after stopping shop %s", shop_id)

        return True

    async def start_all_online_shops(self) -> int:
        with get_sync_session() as session:
            rows = session.scalars(
                select(ShopTable.id).where(
                    ShopTable.is_online.is_(True),
                )
            ).all()

        tasks: list[Awaitable[bool]] = []
        for row in rows:
            shop_id = str(row)
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


class ShopWorker:
    """Dedicated worker process owning one Playwright runtime and multiple shops."""

    def __init__(
        self,
        worker_id: int,
        cmd_queue: Queue[Command],
        status_queue: Queue[StatusEvent],
    ) -> None:
        self._worker_id = worker_id
        self._cmd_queue = cmd_queue
        self._status_queue = status_queue
        self._runtime = ShopRuntime(worker_id=worker_id, status_queue=status_queue)
        self._shutdown = False

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run_async())
        finally:
            pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()

    async def _emit_heartbeat(self) -> None:
        try:
            info = await _wait(engine.get_memory_info(), timeout_seconds=DEFAULT_OPERATION_TIMEOUT_SECONDS)
            memory_mb = float(info.get("rss_mb", 0.0))
        except Exception:
            logger.exception("Worker %s failed to collect heartbeat memory info", self._worker_id)
            memory_mb = 0.0
        self._status_queue.put_nowait(
            WorkerHeartbeat(
                worker_id=self._worker_id,
                shop_count=len(self._runtime.get_running_shops()),
                memory_mb=memory_mb,
            )
        )

    def _next_command_blocking(self, timeout_seconds: float) -> Command | None:
        try:
            return self._cmd_queue.get(timeout=timeout_seconds)
        except Empty:
            return None

    async def _handle_command(self, command: Command) -> None:
        if isinstance(command, StartShop):
            await self._runtime.start_shop(command.shop_id, proxy=command.proxy)
            return
        if isinstance(command, StopShop):
            await self._runtime.stop_shop(command.shop_id)
            return
        if isinstance(command, Shutdown):
            self._shutdown = True
            await self._runtime.stop_all_shops()
            if engine.is_running:
                await _wait(engine.stop(), timeout_seconds=DEFAULT_ENGINE_TIMEOUT_SECONDS)
            return
        logger.warning("Worker %s received unsupported command: %r", self._worker_id, command)

    async def _run_async(self) -> None:
        heartbeat_interval = _env_float("WORKER_HEARTBEAT_INTERVAL", DEFAULT_WORKER_HEARTBEAT_INTERVAL_SECONDS)
        poll_timeout = min(DEFAULT_COMMAND_POLL_TIMEOUT_SECONDS, max(0.1, heartbeat_interval))
        loop = asyncio.get_running_loop()
        last_heartbeat = 0.0

        while not self._shutdown:
            now = loop.time()
            if now - last_heartbeat >= heartbeat_interval:
                await self._emit_heartbeat()
                last_heartbeat = now

            command = await _wait(
                asyncio.to_thread(self._next_command_blocking, poll_timeout),
                timeout_seconds=poll_timeout + 1.0,
            )
            if command is None:
                continue
            await self._handle_command(command)


def worker_main(
    worker_id: int,
    cmd_queue: Queue[Command],
    status_queue: Queue[StatusEvent],
) -> None:
    """Multiprocessing entrypoint for one shop worker."""

    load_dotenv()
    worker = ShopWorker(worker_id=worker_id, cmd_queue=cmd_queue, status_queue=status_queue)
    worker.run()
