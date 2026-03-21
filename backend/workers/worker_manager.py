"""Main-process worker lifecycle and shop assignment manager."""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from multiprocessing import get_context
from multiprocessing.context import BaseContext
from multiprocessing.process import BaseProcess
from multiprocessing.queues import Queue
from queue import Empty, Full

from sqlalchemy import func, select

from backend.db.database import get_sync_session
from backend.db.orm import ShopTable
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
from backend.workers.shop_worker import worker_main


logger = logging.getLogger(__name__)

DEFAULT_MAX_SHOPS_PER_WORKER = 5
DEFAULT_WORKER_QUEUE_MAXSIZE = 100
DEFAULT_WORKER_JOIN_TIMEOUT_SECONDS = 30.0
DEFAULT_STATUS_POLL_TIMEOUT_SECONDS = 1.0


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid integer env %s=%r, using default %s", name, value, default)
        return default


def _shop_exists(shop_id: str) -> bool:
    with get_sync_session() as session:
        return session.get(ShopTable, shop_id) is not None


def _online_shop_count() -> int:
    with get_sync_session() as session:
        rows = session.scalar(
            select(func.count(ShopTable.id)).where(
                ShopTable.is_online.is_(True),
                ShopTable.ai_enabled.is_(True),
            )
        )
    return int(rows or 0)


def _apply_shop_status(shop_id: str, **kwargs: object) -> None:
    if not kwargs:
        return

    allowed_fields = {"is_online", "cookie_valid", "last_active_at"}
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

        if updated:
            shop.updated_at = datetime.now().isoformat()


@dataclass(slots=True)
class WorkerHandle:
    process: BaseProcess
    cmd_queue: Queue[Command]
    shop_ids: set[str] = field(default_factory=set)
    last_heartbeat_at: float = 0.0
    memory_mb: float = 0.0


class WorkerManager:
    """Owns worker processes, assignment state, and status handling."""

    def __init__(
        self,
        *,
        max_shops_per_worker: int | None = None,
        queue_maxsize: int | None = None,
        mp_context: BaseContext | None = None,
    ) -> None:
        self._max_shops_per_worker = max_shops_per_worker or _env_int(
            "MAX_SHOPS_PER_WORKER",
            DEFAULT_MAX_SHOPS_PER_WORKER,
        )
        self._queue_maxsize = queue_maxsize or _env_int("WORKER_QUEUE_MAXSIZE", DEFAULT_WORKER_QUEUE_MAXSIZE)
        self._ctx = mp_context or get_context("spawn")
        self._status_queue: Queue[StatusEvent] = self._ctx.Queue(maxsize=self._queue_maxsize)
        self._workers: dict[int, WorkerHandle] = {}
        self._shop_to_worker: dict[str, int] = {}
        self._next_worker_id = 1
        self._listener_thread: threading.Thread | None = None
        self._listener_stop = threading.Event()
        self._lock = threading.RLock()

    @property
    def max_shops_per_worker(self) -> int:
        return self._max_shops_per_worker

    def required_worker_count(self, shop_count: int) -> int:
        if shop_count <= 0:
            return 0
        return int(math.ceil(shop_count / self._max_shops_per_worker))

    def online_shop_count(self) -> int:
        return _online_shop_count()

    def start_workers(self, n: int) -> int:
        if n <= 0:
            return len(self._workers)

        with self._lock:
            while len(self._workers) < n:
                worker_id = self._next_worker_id
                self._next_worker_id += 1
                self._workers[worker_id] = self._spawn_worker(worker_id)
        return len(self._workers)

    def ensure_worker_capacity(self, total_shops: int) -> int:
        return self.start_workers(self.required_worker_count(total_shops))

    def start_status_listener(self) -> None:
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        self._listener_stop.clear()
        self._listener_thread = threading.Thread(
            target=self._status_listener,
            name="worker-status-listener",
            daemon=True,
        )
        self._listener_thread.start()

    def assign_shop(self, shop_id: str) -> bool:
        if not _shop_exists(shop_id):
            return False

        with self._lock:
            if shop_id in self._shop_to_worker:
                return False

            worker_id, handle = self._pick_worker_for_assignment()
            self._send_command(handle.cmd_queue, StartShop(shop_id=shop_id))
            handle.shop_ids.add(shop_id)
            self._shop_to_worker[shop_id] = worker_id
            return True

    def remove_shop(self, shop_id: str) -> bool:
        with self._lock:
            worker_id = self._shop_to_worker.pop(shop_id, None)
            if worker_id is None:
                return False

            handle = self._workers.get(worker_id)
            if handle is None:
                return False

            handle.shop_ids.discard(shop_id)
            self._send_command(handle.cmd_queue, StopShop(shop_id=shop_id))
            return True

    def get_running_shops(self) -> list[str]:
        with self._lock:
            return sorted(self._shop_to_worker.keys())

    def get_shop_to_worker(self) -> dict[str, int]:
        with self._lock:
            return dict(self._shop_to_worker)

    def shutdown(self) -> None:
        self._listener_stop.set()

        with self._lock:
            worker_items = list(self._workers.items())

        for _, handle in worker_items:
            self._safe_send_shutdown(handle)

        for _, handle in worker_items:
            self._join_or_kill(handle.process)

        if self._listener_thread is not None:
            self._listener_thread.join(timeout=5.0)
            self._listener_thread = None

        with self._lock:
            self._workers.clear()
            self._shop_to_worker.clear()

    def _spawn_worker(self, worker_id: int) -> WorkerHandle:
        cmd_queue: Queue[Command] = self._ctx.Queue(maxsize=self._queue_maxsize)
        process = self._ctx.Process(
            target=worker_main,
            args=(worker_id, cmd_queue, self._status_queue),
            name=f"shop-worker-{worker_id}",
        )
        process.start()
        logger.info("Started worker %s with pid=%s", worker_id, process.pid)
        return WorkerHandle(process=process, cmd_queue=cmd_queue)

    def _pick_worker_for_assignment(self) -> tuple[int, WorkerHandle]:
        alive_workers = [
            (worker_id, handle)
            for worker_id, handle in self._workers.items()
            if handle.process.is_alive() and len(handle.shop_ids) < self._max_shops_per_worker
        ]
        if alive_workers:
            return min(alive_workers, key=lambda item: (len(item[1].shop_ids), item[0]))

        worker_id = self._next_worker_id
        self._next_worker_id += 1
        handle = self._spawn_worker(worker_id)
        self._workers[worker_id] = handle
        return worker_id, handle

    def _send_command(self, cmd_queue: Queue[Command], command: Command) -> None:
        try:
            cmd_queue.put(command, timeout=DEFAULT_STATUS_POLL_TIMEOUT_SECONDS)
        except Full as exc:
            raise RuntimeError("Worker command queue is full") from exc

    def _safe_send_shutdown(self, handle: WorkerHandle) -> None:
        if not handle.process.is_alive():
            return
        try:
            self._send_command(handle.cmd_queue, Shutdown())
        except Exception:
            logger.exception("Failed to send shutdown command to worker pid=%s", handle.process.pid)

    def _join_or_kill(self, process: BaseProcess) -> None:
        process.join(timeout=DEFAULT_WORKER_JOIN_TIMEOUT_SECONDS)
        if process.is_alive():
            logger.warning("Worker pid=%s did not exit in time, killing", process.pid)
            process.kill()
            process.join(timeout=5.0)

    def _status_listener(self) -> None:
        while not self._listener_stop.is_set():
            try:
                event = self._status_queue.get(timeout=DEFAULT_STATUS_POLL_TIMEOUT_SECONDS)
            except Empty:
                self._monitor_workers()
                continue

            try:
                self._handle_status_event(event)
            except Exception:
                logger.exception("Failed to process worker status event: %r", event)
            self._monitor_workers()

    def _handle_status_event(self, event: StatusEvent) -> None:
        if isinstance(event, WorkerHeartbeat):
            with self._lock:
                handle = self._workers.get(event.worker_id)
                if handle is None:
                    return
                handle.last_heartbeat_at = time.time()
                handle.memory_mb = event.memory_mb
            return

        if isinstance(event, ShopOnline):
            _apply_shop_status(
                event.shop_id,
                is_online=True,
                cookie_valid=True,
                last_active_at=datetime.now().isoformat(),
            )
            return

        if isinstance(event, ShopLoginFailed):
            _apply_shop_status(event.shop_id, is_online=False, cookie_valid=False)
            return

        if isinstance(event, ShopOffline):
            _apply_shop_status(event.shop_id, is_online=False)
            return

        if isinstance(event, ShopCrashRecovery):
            logger.warning(
                "[%s] Worker %s crash recovery attempt %s",
                event.shop_id,
                event.worker_id,
                event.attempt,
            )

    def _monitor_workers(self) -> None:
        restarts: list[tuple[int, list[str]]] = []

        with self._lock:
            for worker_id, handle in list(self._workers.items()):
                if handle.process.is_alive():
                    continue
                affected_shops = sorted(handle.shop_ids)
                logger.warning(
                    "Worker %s exited unexpectedly with code=%s, recovering %s shops",
                    worker_id,
                    handle.process.exitcode,
                    len(affected_shops),
                )
                self._workers.pop(worker_id, None)
                for shop_id in affected_shops:
                    self._shop_to_worker.pop(shop_id, None)
                restarts.append((worker_id, affected_shops))

        for worker_id, shop_ids in restarts:
            handle = self._spawn_worker(worker_id)
            with self._lock:
                self._workers[worker_id] = handle
                if worker_id >= self._next_worker_id:
                    self._next_worker_id = worker_id + 1
                for shop_id in shop_ids:
                    handle.shop_ids.add(shop_id)
                    self._shop_to_worker[shop_id] = worker_id
                    self._send_command(handle.cmd_queue, StartShop(shop_id=shop_id))
