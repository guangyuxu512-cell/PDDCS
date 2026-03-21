from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import shops as shops_api
from backend.db import database
from backend.main import app
from backend.services import scheduler


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


def _insert_shop(shop_id: str, *, is_online: int = 1, ai_enabled: int = 1) -> None:
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, is_online, ai_enabled) VALUES (?,?,?,?,?,?,?)",
            (shop_id, f"店铺-{shop_id}", "pdd", "seller", "secret", is_online, ai_enabled),
        )
        conn.execute("INSERT INTO shop_configs (shop_id) VALUES (?)", (shop_id,))


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "scheduler-browser-close.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    _insert_shop("shop-1")
    yield db_path
    _cleanup_database_files(db_path)


@pytest.fixture()
def client(isolated_database: Path) -> Iterator[TestClient]:
    del isolated_database
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_shop_loop_stops_gracefully_when_browser_closed_externally(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()

    class FakeCookieManager:
        async def save(self, shop_id: str, current_context: object) -> None:
            del shop_id, current_context
            return None

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self._contexts: dict[str, object] = {}
            self._cookie_manager = FakeCookieManager()
            self.open_calls: list[tuple[str, str]] = []
            self.restart_calls: list[tuple[str, str]] = []
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            self.open_calls.append((shop_id, proxy))
            self._contexts[shop_id] = object()
            return object()

        async def is_context_alive(self, shop_id: str) -> bool:
            self._contexts.pop(shop_id, None)
            return False

        async def restart_shop(self, shop_id: str, proxy: str = "") -> object:
            self.restart_calls.append((shop_id, proxy))
            return object()

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        async def navigate_to_chat(self) -> None:
            return None

        async def is_logged_in(self) -> bool:
            return True

        async def get_session_list(self) -> list[object]:
            raise AssertionError("get_session_list should not run after external browser close")

    fake_engine = FakeEngine()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "")
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: FakeAdapter())

    await shop_scheduler._shop_loop("shop-1")

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0
    assert row["cookie_valid"] == 0
    assert fake_engine.open_calls == [("shop-1", "")]
    assert fake_engine.restart_calls == []
    assert fake_engine.closed_shops == ["shop-1"]


@pytest.mark.asyncio
async def test_stop_shop_force_closes_context_when_task_cancel_times_out(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self.closed_shops: list[str] = []

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    async def stubborn_task() -> None:
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                raise

    fake_engine = FakeEngine()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "DEFAULT_OPERATION_TIMEOUT_SECONDS", 0.01)

    task = asyncio.create_task(stubborn_task())
    await asyncio.sleep(0)
    shop_scheduler._running_tasks["shop-1"] = task

    stopped = await shop_scheduler.stop_shop("shop-1")

    assert stopped is True
    assert fake_engine.closed_shops == ["shop-1"]

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_stop_endpoint_returns_success_when_task_already_finished(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_stop_shop(shop_id: str) -> bool:
        return False

    monkeypatch.setattr(shops_api, "stop_shop", fake_stop_shop)

    response = client.post("/api/shops/shop-1/stop")

    assert response.json() == {"code": 0, "msg": "ok", "data": None}
    with database.get_db() as conn:
        row = conn.execute("SELECT is_online FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0
