from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.db import database
from backend.services import scheduler


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "scheduler.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, is_online, ai_enabled) VALUES (?,?,?,?,?,?,?)",
            ("shop-1", "测试店铺", "pdd", "seller", "secret", 1, 1),
        )
        conn.execute("INSERT INTO shop_configs (shop_id) VALUES (?)", ("shop-1",))
    yield db_path
    _cleanup_database_files(db_path)


@pytest.mark.asyncio
async def test_start_and_stop_shop_manage_task_lifecycle(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    task_started = asyncio.Event()
    task_cancelled = asyncio.Event()
    shop_scheduler = scheduler.ShopScheduler()

    async def fake_shop_loop(shop_id: str) -> None:
        assert shop_id == "shop-1"
        task_started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            task_cancelled.set()
            raise

    monkeypatch.setattr(shop_scheduler, "_shop_loop", fake_shop_loop)

    started = await shop_scheduler.start_shop("shop-1")
    assert started is True
    await asyncio.wait_for(task_started.wait(), timeout=1.0)
    assert shop_scheduler.get_running_shops() == ["shop-1"]

    duplicate = await shop_scheduler.start_shop("shop-1")
    assert duplicate is False

    stopped = await shop_scheduler.stop_shop("shop-1")
    assert stopped is True
    await asyncio.wait_for(task_cancelled.wait(), timeout=1.0)
    assert shop_scheduler.get_running_shops() == []


@pytest.mark.asyncio
async def test_start_shop_returns_false_for_missing_shop(isolated_database: Path) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    started = await shop_scheduler.start_shop("missing-shop")
    assert started is False


@pytest.mark.asyncio
async def test_shop_loop_uses_open_shop_proxy_and_close_shop(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: dict[str, object] = {}
    open_called = asyncio.Event()
    shop_scheduler = scheduler.ShopScheduler()

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            calls["open_shop"] = (shop_id, proxy)
            open_called.set()
            return object()

        async def close_shop(self, shop_id: str) -> None:
            calls["close_shop"] = shop_id

    class FakeAdapter:
        async def navigate_to_chat(self) -> None:
            return None

        async def is_logged_in(self) -> bool:
            return True

        async def get_session_list(self) -> list[object]:
            await asyncio.sleep(60)
            return []

    monkeypatch.setattr(scheduler, "engine", FakeEngine())
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "http://127.0.0.1:7890")
    monkeypatch.setattr(
        scheduler,
        "_load_runtime_configuration",
        lambda shop_id: ({}, object()),
    )
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: FakeAdapter())

    task = asyncio.create_task(shop_scheduler._shop_loop("shop-1"))
    await asyncio.wait_for(open_called.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert calls["open_shop"] == ("shop-1", "http://127.0.0.1:7890")
    assert calls["close_shop"] == "shop-1"
