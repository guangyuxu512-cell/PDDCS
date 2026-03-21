"""Shop scheduler compatibility layer with worker-manager orchestration."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from typing import Any, TypeVar

from sqlalchemy import select

from backend.ai.llm_client import LlmClient
from backend.db.database import get_sync_session
from backend.db.orm import ShopTable
from backend.engines.playwright_engine import engine
from backend.services.message_processor import process_buyer_message
from backend.services.shop_service import get_shop_config
from backend.workers import shop_worker as runtime_module
from backend.workers.shop_worker import ShopRuntime
from backend.workers.worker_manager import WorkerManager


_RUNTIME_ENV_FLOAT = runtime_module._env_float
_RUNTIME_WAIT = runtime_module._wait
_RUNTIME_SLEEP = runtime_module._sleep
_RUNTIME_IS_SHOP_CONTEXT_ALIVE = runtime_module._is_shop_context_alive
_RUNTIME_GET_SHOP_PLATFORM = runtime_module._get_shop_platform
_RUNTIME_LOAD_RUNTIME_CONFIGURATION = runtime_module._load_runtime_configuration
_RUNTIME_GET_SHOP_CREDENTIALS = runtime_module._get_shop_credentials
_RUNTIME_UPDATE_ESCALATION_LOG = runtime_module._update_escalation_log
_RUNTIME_UPDATE_SHOP_STATUS = runtime_module._update_shop_status
_RUNTIME_GET_SHOP_CONTEXT = runtime_module._get_shop_context
_RUNTIME_SAVE_SHOP_COOKIES = runtime_module._save_shop_cookies


DEFAULT_POLL_INTERVAL_SECONDS = runtime_module.DEFAULT_POLL_INTERVAL_SECONDS
DEFAULT_OPERATION_TIMEOUT_SECONDS = runtime_module.DEFAULT_OPERATION_TIMEOUT_SECONDS
DEFAULT_ENGINE_TIMEOUT_SECONDS = runtime_module.DEFAULT_ENGINE_TIMEOUT_SECONDS
DEFAULT_NAVIGATION_TIMEOUT_SECONDS = runtime_module.DEFAULT_NAVIGATION_TIMEOUT_SECONDS
DEFAULT_LOGIN_TIMEOUT_SECONDS = runtime_module.DEFAULT_LOGIN_TIMEOUT_SECONDS
DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS = runtime_module.DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS
DEFAULT_LOGIN_CHECK_INTERVAL = runtime_module.DEFAULT_LOGIN_CHECK_INTERVAL
DEFAULT_COOKIE_SAVE_INTERVAL = runtime_module.DEFAULT_COOKIE_SAVE_INTERVAL
DEFAULT_MEMORY_CLEANUP_INTERVAL = runtime_module.DEFAULT_MEMORY_CLEANUP_INTERVAL
DEFAULT_CRASH_RECOVERY_MAX_RETRIES = runtime_module.DEFAULT_CRASH_RECOVERY_MAX_RETRIES
T = TypeVar("T")


def _env_float(name: str, default: float) -> float:
    return _RUNTIME_ENV_FLOAT(name, default)


async def _wait(awaitable: Awaitable[T], timeout_seconds: float) -> T:
    return await _RUNTIME_WAIT(awaitable, timeout_seconds)


async def _sleep(seconds: float) -> None:
    await _RUNTIME_SLEEP(seconds)


async def _is_shop_context_alive(shop_id: str) -> bool:
    return await _RUNTIME_IS_SHOP_CONTEXT_ALIVE(shop_id)


def _get_shop_platform(shop_id: str) -> str | None:
    return _RUNTIME_GET_SHOP_PLATFORM(shop_id)


def _load_runtime_configuration(shop_id: str) -> tuple[dict[str, Any], LlmClient]:
    return _RUNTIME_LOAD_RUNTIME_CONFIGURATION(shop_id)


def _get_shop_credentials(shop_id: str) -> tuple[str, str]:
    return _RUNTIME_GET_SHOP_CREDENTIALS(shop_id)


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
    _RUNTIME_UPDATE_ESCALATION_LOG(session_id, shop_id, success)


def _update_shop_status(shop_id: str, **kwargs: Any) -> None:
    _RUNTIME_UPDATE_SHOP_STATUS(shop_id, **kwargs)


def _get_shop_context(shop_id: str) -> Any | None:
    return _RUNTIME_GET_SHOP_CONTEXT(shop_id)


async def _save_shop_cookies(shop_id: str) -> None:
    await _RUNTIME_SAVE_SHOP_COOKIES(shop_id)


def _sync_runtime_module() -> None:
    runtime_module.engine = engine
    runtime_module.process_buyer_message = process_buyer_message
    runtime_module.get_shop_config = get_shop_config
    runtime_module.DEFAULT_POLL_INTERVAL_SECONDS = DEFAULT_POLL_INTERVAL_SECONDS
    runtime_module.DEFAULT_OPERATION_TIMEOUT_SECONDS = DEFAULT_OPERATION_TIMEOUT_SECONDS
    runtime_module.DEFAULT_ENGINE_TIMEOUT_SECONDS = DEFAULT_ENGINE_TIMEOUT_SECONDS
    runtime_module.DEFAULT_NAVIGATION_TIMEOUT_SECONDS = DEFAULT_NAVIGATION_TIMEOUT_SECONDS
    runtime_module.DEFAULT_LOGIN_TIMEOUT_SECONDS = DEFAULT_LOGIN_TIMEOUT_SECONDS
    runtime_module.DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS = DEFAULT_MESSAGE_PROCESS_TIMEOUT_SECONDS
    runtime_module.DEFAULT_LOGIN_CHECK_INTERVAL = DEFAULT_LOGIN_CHECK_INTERVAL
    runtime_module.DEFAULT_COOKIE_SAVE_INTERVAL = DEFAULT_COOKIE_SAVE_INTERVAL
    runtime_module.DEFAULT_MEMORY_CLEANUP_INTERVAL = DEFAULT_MEMORY_CLEANUP_INTERVAL
    runtime_module.DEFAULT_CRASH_RECOVERY_MAX_RETRIES = DEFAULT_CRASH_RECOVERY_MAX_RETRIES
    runtime_module._env_float = _env_float
    runtime_module._wait = _wait
    runtime_module._sleep = _sleep
    runtime_module._is_shop_context_alive = _is_shop_context_alive
    runtime_module._get_shop_platform = _get_shop_platform
    runtime_module._load_runtime_configuration = _load_runtime_configuration
    runtime_module._get_shop_credentials = _get_shop_credentials
    runtime_module._get_shop_restart_policy = _get_shop_restart_policy
    runtime_module._get_shop_force_online = _get_shop_force_online
    runtime_module._get_shop_proxy = _get_shop_proxy
    runtime_module._update_escalation_log = _update_escalation_log
    runtime_module._update_shop_status = _update_shop_status
    runtime_module._get_shop_context = _get_shop_context
    runtime_module._save_shop_cookies = _save_shop_cookies


def _online_shop_ids() -> list[str]:
    with get_sync_session() as session:
        rows = session.scalars(
            select(ShopTable.id).where(
                ShopTable.is_online.is_(True),
            )
        ).all()
    return [str(row) for row in rows]


class ShopScheduler(ShopRuntime):
    """Compatibility wrapper around worker-based scheduling."""

    def __init__(self, worker_manager: WorkerManager | None = None) -> None:
        _sync_runtime_module()
        super().__init__(worker_id=0, status_queue=None)
        self._worker_manager = worker_manager

    def _using_worker_manager(self) -> bool:
        return self._worker_manager is not None

    def _sync_for_runtime(self) -> None:
        _sync_runtime_module()

    def _on_task_done(self, shop_id: str, task: asyncio.Task[None]) -> None:
        self._sync_for_runtime()
        super()._on_task_done(shop_id, task)

    async def _auto_restart_shop(self, shop_id: str) -> None:
        self._sync_for_runtime()
        await super()._auto_restart_shop(shop_id)

    async def _process_session(
        self,
        shop_id: str,
        adapter: Any,
        session_info: Any,
        shop_config: dict[str, Any],
        llm_client: LlmClient,
    ) -> None:
        self._sync_for_runtime()
        await super()._process_session(shop_id, adapter, session_info, shop_config, llm_client)

    async def _shop_loop(self, shop_id: str) -> None:
        self._sync_for_runtime()
        await super()._shop_loop(shop_id)

    def get_running_shops(self) -> list[str]:
        if self._using_worker_manager():
            return self._worker_manager.get_running_shops()  # type: ignore[union-attr]
        return super().get_running_shops()

    async def start_shop(self, shop_id: str) -> bool:
        if self._using_worker_manager():
            return self._worker_manager.assign_shop(shop_id)  # type: ignore[union-attr]
        self._sync_for_runtime()
        return await super().start_shop(shop_id)

    async def stop_shop(self, shop_id: str) -> bool:
        if self._using_worker_manager():
            return self._worker_manager.remove_shop(shop_id)  # type: ignore[union-attr]
        self._sync_for_runtime()
        return await super().stop_shop(shop_id)

    async def start_all_online_shops(self) -> int:
        if not self._using_worker_manager():
            self._sync_for_runtime()
            return await super().start_all_online_shops()

        started = 0
        for shop_id in _online_shop_ids():
            if self._worker_manager.assign_shop(shop_id):  # type: ignore[union-attr]
                started += 1
        return started

    async def stop_all_shops(self) -> int:
        if not self._using_worker_manager():
            self._sync_for_runtime()
            return await super().stop_all_shops()

        stopped = 0
        for shop_id in self._worker_manager.get_running_shops():  # type: ignore[union-attr]
            if self._worker_manager.remove_shop(shop_id):  # type: ignore[union-attr]
                stopped += 1
        return stopped


_DEFAULT_WORKER_MANAGER: WorkerManager | None = None
_DEFAULT_SCHEDULER = ShopScheduler()


def configure_worker_manager(worker_manager: WorkerManager | None) -> ShopScheduler:
    global _DEFAULT_WORKER_MANAGER, _DEFAULT_SCHEDULER

    _DEFAULT_WORKER_MANAGER = worker_manager
    _DEFAULT_SCHEDULER = ShopScheduler(worker_manager=worker_manager)
    return _DEFAULT_SCHEDULER


def get_worker_manager() -> WorkerManager | None:
    return _DEFAULT_WORKER_MANAGER


def get_scheduler() -> ShopScheduler:
    return _DEFAULT_SCHEDULER


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
