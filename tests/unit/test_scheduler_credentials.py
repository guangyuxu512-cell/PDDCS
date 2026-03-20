from __future__ import annotations

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
    db_path = db_dir / "scheduler-credentials.db"
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
async def test_navigate_adapter_to_chat_passes_db_credentials_to_supported_adapter(
    isolated_database: Path,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    calls: list[tuple[str, str]] = []

    class CredentialAdapter:
        async def navigate_to_chat(self, username: str = "", password: str = "") -> None:
            calls.append((username, password))

    used_credentials = await shop_scheduler._navigate_adapter_to_chat("shop-1", CredentialAdapter())  # type: ignore[arg-type]

    assert used_credentials is True
    assert calls == [("seller", "secret")]


@pytest.mark.asyncio
async def test_navigate_adapter_to_chat_falls_back_for_legacy_adapter(
    isolated_database: Path,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    calls: list[str] = []

    class LegacyAdapter:
        async def navigate_to_chat(self) -> None:
            calls.append("called")

    used_credentials = await shop_scheduler._navigate_adapter_to_chat("shop-1", LegacyAdapter())  # type: ignore[arg-type]

    assert used_credentials is False
    assert calls == ["called"]
