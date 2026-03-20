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
    db_path = db_dir / "shop-lifecycle.db"
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


def test_shop_api_exposes_memory_and_bulk_lifecycle_endpoints(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        async def get_memory_info(self) -> dict[str, object]:
            return {
                "active_shops": 2,
                "shop_details": {"shop-1": {"pages": 1, "uptime_seconds": 12.5}},
                "rss_mb": 128.0,
                "system_memory_percent": 45.0,
            }

    async def fake_start_all_online_shops() -> int:
        return 2

    async def fake_stop_all_shops() -> int:
        return 1

    monkeypatch.setattr(shops_api, "engine", FakeEngine())
    monkeypatch.setattr(scheduler, "start_all_online_shops", fake_start_all_online_shops)
    monkeypatch.setattr(scheduler, "stop_all_shops", fake_stop_all_shops)

    memory_response = client.get("/api/shops/memory")
    assert memory_response.json() == {
        "code": 0,
        "msg": "ok",
        "data": {
            "active_shops": 2,
            "shop_details": {"shop-1": {"pages": 1, "uptime_seconds": 12.5}},
            "rss_mb": 128.0,
            "system_memory_percent": 45.0,
        },
    }

    start_all_response = client.post("/api/shops/start-all")
    assert start_all_response.json() == {"code": 0, "msg": "ok", "data": {"started": 2}}

    stop_all_response = client.post("/api/shops/stop-all")
    assert stop_all_response.json() == {"code": 0, "msg": "ok", "data": {"stopped": 1}}


@pytest.mark.asyncio
async def test_shop_startup_saves_cookie_and_marks_shop_online(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    first_poll_started = asyncio.Event()
    context = object()

    class FakeCookieManager:
        def __init__(self) -> None:
            self.saved: list[tuple[str, object]] = []

        async def save(self, shop_id: str, current_context: object) -> None:
            self.saved.append((shop_id, current_context))

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self._contexts: dict[str, object] = {}
            self._cookie_manager = FakeCookieManager()
            self.open_calls: list[tuple[str, str]] = []
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            self.open_calls.append((shop_id, proxy))
            self._contexts[shop_id] = context
            return object()

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        async def navigate_to_chat(self) -> None:
            return None

        async def is_logged_in(self) -> bool:
            return True

        async def get_session_list(self) -> list[object]:
            first_poll_started.set()
            await asyncio.sleep(60)
            return []

    fake_engine = FakeEngine()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "http://127.0.0.1:7890")
    monkeypatch.setattr(scheduler, "_load_runtime_configuration", lambda shop_id: ({}, object()))
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: FakeAdapter())

    task = asyncio.create_task(shop_scheduler._shop_loop("shop-1"))
    await asyncio.wait_for(first_poll_started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 1
    assert row["cookie_valid"] == 1
    assert fake_engine.open_calls == [("shop-1", "http://127.0.0.1:7890")]
    assert fake_engine.closed_shops == ["shop-1"]
    assert fake_engine._cookie_manager.saved == [("shop-1", context)]


@pytest.mark.asyncio
async def test_shop_startup_login_timeout_marks_shop_offline(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()

    class FakeCookieManager:
        async def save(self, shop_id: str, current_context: object) -> None:
            raise AssertionError("save should not be called when login fails")

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self._contexts: dict[str, object] = {"shop-1": object()}
            self._cookie_manager = FakeCookieManager()
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            return object()

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        def __init__(self) -> None:
            self.wait_calls: list[int] = []

        async def navigate_to_chat(self) -> None:
            return None

        async def is_logged_in(self) -> bool:
            return False

        async def wait_for_login(self, timeout_ms: int = 120000) -> bool:
            self.wait_calls.append(timeout_ms)
            return False

    fake_engine = FakeEngine()
    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "")
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: fake_adapter)

    await shop_scheduler._shop_loop("shop-1")

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0
    assert row["cookie_valid"] == 0
    assert fake_adapter.wait_calls == [120000]
    assert fake_engine.closed_shops == ["shop-1"]


@pytest.mark.asyncio
async def test_login_health_check_detects_expired_session_and_recovers(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    first_poll_started = asyncio.Event()
    context = object()

    class FakeCookieManager:
        def __init__(self) -> None:
            self.saved: list[tuple[str, object]] = []

        async def save(self, shop_id: str, current_context: object) -> None:
            self.saved.append((shop_id, current_context))

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self._contexts: dict[str, object] = {}
            self._cookie_manager = FakeCookieManager()
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            self._contexts[shop_id] = context
            return object()

        async def cleanup_extra_pages(self, shop_id: str) -> int:
            raise AssertionError("cleanup_extra_pages should not run in this test")

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        def __init__(self) -> None:
            self.navigate_calls = 0
            self.wait_calls: list[int] = []
            self.login_results = [True, False, False]

        async def navigate_to_chat(self) -> None:
            self.navigate_calls += 1

        async def is_logged_in(self) -> bool:
            return self.login_results.pop(0)

        async def wait_for_login(self, timeout_ms: int = 120000) -> bool:
            self.wait_calls.append(timeout_ms)
            return True

        async def get_session_list(self) -> list[object]:
            first_poll_started.set()
            await asyncio.sleep(60)
            return []

    fake_engine = FakeEngine()
    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "")
    monkeypatch.setattr(scheduler, "_load_runtime_configuration", lambda shop_id: ({}, object()))
    monkeypatch.setattr(scheduler, "DEFAULT_LOGIN_CHECK_INTERVAL", 1)
    monkeypatch.setattr(scheduler, "DEFAULT_COOKIE_SAVE_INTERVAL", 3600.0)
    monkeypatch.setattr(scheduler, "DEFAULT_MEMORY_CLEANUP_INTERVAL", 3600.0)
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: fake_adapter)

    task = asyncio.create_task(shop_scheduler._shop_loop("shop-1"))
    await asyncio.wait_for(first_poll_started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 1
    assert row["cookie_valid"] == 1
    assert fake_adapter.navigate_calls == 2
    assert fake_adapter.wait_calls == [120000]
    assert fake_engine._cookie_manager.saved == [("shop-1", context), ("shop-1", context)]
    assert fake_engine.closed_shops == ["shop-1"]


@pytest.mark.asyncio
async def test_crash_recovery_stops_after_max_retries(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self.restart_calls: list[tuple[str, str]] = []
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            return object()

        async def restart_shop(self, shop_id: str, proxy: str = "") -> object:
            self.restart_calls.append((shop_id, proxy))
            return object()

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class CrashAdapter:
        async def navigate_to_chat(self) -> None:
            raise RuntimeError("boom")

    async def no_sleep(seconds: float) -> None:
        del seconds
        return None

    fake_engine = FakeEngine()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_sleep", no_sleep)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "http://127.0.0.1:7890")
    monkeypatch.setattr(scheduler, "DEFAULT_CRASH_RECOVERY_MAX_RETRIES", 1)
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: CrashAdapter())

    await shop_scheduler._shop_loop("shop-1")

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0
    assert row["cookie_valid"] == 0
    assert fake_engine.restart_calls == [("shop-1", "http://127.0.0.1:7890")]
    assert fake_engine.closed_shops == ["shop-1"]


@pytest.mark.asyncio
async def test_start_all_online_shops_runs_in_parallel(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    _insert_shop("shop-2")
    shop_scheduler = scheduler.ShopScheduler()
    both_started = asyncio.Event()
    release = asyncio.Event()
    started_shop_ids: list[str] = []

    async def fake_start_shop(shop_id: str) -> bool:
        started_shop_ids.append(shop_id)
        if len(started_shop_ids) == 2:
            both_started.set()
        await release.wait()
        return True

    monkeypatch.setattr(shop_scheduler, "start_shop", fake_start_shop)

    task = asyncio.create_task(shop_scheduler.start_all_online_shops())
    await asyncio.wait_for(both_started.wait(), timeout=1.0)
    release.set()
    count = await asyncio.wait_for(task, timeout=1.0)

    assert set(started_shop_ids) == {"shop-1", "shop-2"}
    assert count == 2
