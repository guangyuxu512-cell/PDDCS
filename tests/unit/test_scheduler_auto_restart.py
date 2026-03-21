from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.db import database
from backend.services import scheduler
from backend.services.shop_service import get_shop_config, update_shop_config


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
    db_path = db_dir / "scheduler-auto-restart.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    _insert_shop("shop-1")
    yield db_path
    _cleanup_database_files(db_path)


def test_get_shop_restart_policy_returns_false_when_disabled() -> None:
    with patch("backend.services.scheduler.get_shop_config") as mock_config:
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"auto_restart": False}
        mock_config.return_value = mock_model

        assert scheduler._get_shop_restart_policy("shop-1") is False


def test_get_shop_restart_policy_returns_true_when_enabled() -> None:
    with patch("backend.services.scheduler.get_shop_config") as mock_config:
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"auto_restart": True}
        mock_config.return_value = mock_model

        assert scheduler._get_shop_restart_policy("shop-1") is True


def test_get_shop_force_online_returns_true_when_enabled() -> None:
    with patch("backend.services.scheduler.get_shop_config") as mock_config:
        mock_model = MagicMock()
        mock_model.model_dump.return_value = {"force_online": True}
        mock_config.return_value = mock_model

        assert scheduler._get_shop_force_online("shop-1") is True


@pytest.mark.asyncio
async def test_ensure_online_status_skeleton_returns_true() -> None:
    from backend.adapters.pdd import PddAdapter

    page = AsyncMock()
    page.url = "https://mms.pinduoduo.com/chat-merchant/#/"
    page.frames = []
    adapter = PddAdapter(page, "shop-1")

    result = await adapter.ensure_online_status()

    assert result is True


def test_shop_config_round_trip_persists_auto_restart_and_force_online(
    isolated_database: Path,
) -> None:
    del isolated_database

    updated = update_shop_config(
        "shop-1",
        {
            "name": "店铺-shop-1",
            "username": "seller",
            "password": "secret",
            "aiEnabled": True,
            "llmMode": "global",
            "autoRestart": True,
            "forceOnline": True,
        },
    )

    assert updated is not None
    assert updated.auto_restart is True
    assert updated.force_online is True

    loaded = get_shop_config("shop-1")
    assert loaded is not None
    assert loaded.model_dump()["autoRestart"] is True
    assert loaded.model_dump()["forceOnline"] is True


@pytest.mark.asyncio
async def test_shop_loop_restarts_when_browser_closed_externally_and_auto_restart_enabled(
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
            raise RuntimeError("restart failed")

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        async def navigate_to_chat(self) -> None:
            return None

        async def is_logged_in(self) -> bool:
            return True

        async def get_session_list(self) -> list[object]:
            raise AssertionError("get_session_list should not run after external browser close")

    async def no_sleep(seconds: float) -> None:
        del seconds
        return None

    fake_engine = FakeEngine()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_sleep", no_sleep)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "")
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: FakeAdapter())

    update_shop_config(
        "shop-1",
        {
            "name": "店铺-shop-1",
            "username": "seller",
            "password": "secret",
            "aiEnabled": True,
            "llmMode": "global",
            "autoRestart": True,
            "forceOnline": False,
        },
    )

    monkeypatch.setattr(scheduler, "DEFAULT_CRASH_RECOVERY_MAX_RETRIES", 1)

    await shop_scheduler._shop_loop("shop-1")

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0
    assert row["cookie_valid"] == 0
    assert fake_engine.open_calls == [("shop-1", ""), ("shop-1", "")]
    assert fake_engine.restart_calls == [("shop-1", "")]
    assert fake_engine.closed_shops == ["shop-1"]
