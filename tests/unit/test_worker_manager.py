from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from backend.db import database
from backend.workers.protocol import Shutdown, StartShop, StopShop
from backend.workers.worker_manager import WorkerManager


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


def _seed_shop(shop_id: str) -> None:
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, is_online, ai_enabled) VALUES (?,?,?,?,?,?,?)",
            (shop_id, f"店铺-{shop_id}", "pdd", "seller", "secret", 1, 1),
        )
        conn.execute("INSERT INTO shop_configs (shop_id) VALUES (?)", (shop_id,))


class FakeQueue:
    def __init__(self, maxsize: int = 0) -> None:
        self.maxsize = maxsize
        self.items: list[Any] = []

    def put(self, item: Any, timeout: float | None = None) -> None:
        del timeout
        self.items.append(item)

    def put_nowait(self, item: Any) -> None:
        self.items.append(item)


class FakeProcess:
    _next_pid = 1000

    def __init__(self, target: Any, args: tuple[Any, ...], name: str) -> None:
        self.target = target
        self.args = args
        self.name = name
        self.pid = FakeProcess._next_pid
        FakeProcess._next_pid += 1
        self.exitcode: int | None = None
        self._alive = False
        self.join_calls: list[float | None] = []
        self.kill_called = False

    def start(self) -> None:
        self._alive = True

    def is_alive(self) -> bool:
        return self._alive

    def join(self, timeout: float | None = None) -> None:
        self.join_calls.append(timeout)
        self._alive = False

    def kill(self) -> None:
        self.kill_called = True
        self._alive = False
        self.exitcode = -9


class FakeContext:
    def Queue(self, maxsize: int = 0) -> FakeQueue:
        return FakeQueue(maxsize=maxsize)

    def Process(self, target: Any, args: tuple[Any, ...], name: str) -> FakeProcess:
        return FakeProcess(target=target, args=args, name=name)


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "worker-manager.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    yield db_path
    _cleanup_database_files(db_path)


def test_worker_manager_balances_assignments_and_shutdowns_cleanly(isolated_database: Path) -> None:
    del isolated_database
    for shop_id in ("shop-1", "shop-2", "shop-3"):
        _seed_shop(shop_id)

    manager = WorkerManager(max_shops_per_worker=2, mp_context=FakeContext())
    assert manager.start_workers(2) == 2

    assert manager.assign_shop("shop-1") is True
    assert manager.assign_shop("shop-2") is True
    assert manager.assign_shop("shop-3") is True

    mapping = manager.get_shop_to_worker()
    assert set(mapping) == {"shop-1", "shop-2", "shop-3"}

    loads = sorted(len(handle.shop_ids) for handle in manager._workers.values())
    assert loads == [1, 2]

    issued_commands = [
        command
        for handle in manager._workers.values()
        for command in handle.cmd_queue.items
        if isinstance(command, StartShop)
    ]
    assert sorted(command.shop_id for command in issued_commands) == ["shop-1", "shop-2", "shop-3"]

    handles = list(manager._workers.values())
    manager.shutdown()

    for handle in handles:
        assert any(isinstance(command, Shutdown) for command in handle.cmd_queue.items)


def test_worker_manager_restarts_dead_worker_and_restores_assigned_shops(isolated_database: Path) -> None:
    del isolated_database
    for shop_id in ("shop-1", "shop-2"):
        _seed_shop(shop_id)

    manager = WorkerManager(max_shops_per_worker=5, mp_context=FakeContext())
    manager.start_workers(1)
    assert manager.assign_shop("shop-1") is True
    assert manager.assign_shop("shop-2") is True

    original_handle = manager._workers[1]
    original_handle.process._alive = False
    original_handle.process.exitcode = 1

    manager._monitor_workers()

    restarted_handle = manager._workers[1]
    assert restarted_handle is not original_handle
    assert restarted_handle.process.is_alive() is True
    assert manager.get_shop_to_worker() == {"shop-1": 1, "shop-2": 1}

    restored_commands = [
        command for command in restarted_handle.cmd_queue.items if isinstance(command, StartShop)
    ]
    assert sorted(command.shop_id for command in restored_commands) == ["shop-1", "shop-2"]


def test_worker_manager_remove_shop_sends_stop_command(isolated_database: Path) -> None:
    del isolated_database
    _seed_shop("shop-1")

    manager = WorkerManager(max_shops_per_worker=5, mp_context=FakeContext())
    manager.start_workers(1)
    assert manager.assign_shop("shop-1") is True
    assert manager.remove_shop("shop-1") is True

    handle = manager._workers[1]
    assert any(isinstance(command, StopShop) for command in handle.cmd_queue.items)
