"""Multiprocessing protocol for FastAPI main process and shop workers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StartShop:
    """Command telling a worker to start one shop runtime."""

    shop_id: str
    proxy: str = ""


@dataclass(slots=True)
class StopShop:
    """Command telling a worker to stop one shop runtime."""

    shop_id: str


@dataclass(slots=True)
class Shutdown:
    """Command telling a worker to exit gracefully."""


Command = StartShop | StopShop | Shutdown


@dataclass(slots=True)
class ShopOnline:
    """Status emitted when a shop becomes available for polling."""

    shop_id: str
    worker_id: int


@dataclass(slots=True)
class ShopOffline:
    """Status emitted when a shop stops running."""

    shop_id: str
    worker_id: int
    reason: str


@dataclass(slots=True)
class ShopLoginFailed:
    """Status emitted when automatic or manual login fails."""

    shop_id: str
    worker_id: int


@dataclass(slots=True)
class ShopCrashRecovery:
    """Status emitted before one crash recovery retry."""

    shop_id: str
    worker_id: int
    attempt: int


@dataclass(slots=True)
class WorkerHeartbeat:
    """Periodic worker heartbeat for visibility and health checks."""

    worker_id: int
    shop_count: int
    memory_mb: float


StatusEvent = ShopOnline | ShopOffline | ShopLoginFailed | ShopCrashRecovery | WorkerHeartbeat
