from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import shops as shops_api
from backend.db import database
from backend.main import app


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "scheduler-api.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    with TestClient(app) as test_client:
        yield test_client
    _cleanup_database_files(db_path)


def test_scheduler_endpoints_cover_success_and_failure_paths(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_start_shop(shop_id: str) -> bool:
        return shop_id == "shop-1"

    async def fake_stop_shop(shop_id: str) -> bool:
        return shop_id == "shop-1"

    monkeypatch.setattr(shops_api, "start_shop", fake_start_shop)
    monkeypatch.setattr(shops_api, "stop_shop", fake_stop_shop)
    monkeypatch.setattr(shops_api, "get_running_shops", lambda: ["shop-1", "shop-2"])

    start_success = client.post("/api/shops/shop-1/start")
    assert start_success.json() == {"code": 0, "msg": "ok", "data": None}

    start_failure = client.post("/api/shops/missing/start")
    assert start_failure.json() == {"code": -1, "msg": "店铺已在运行中或不存在", "data": None}

    stop_success = client.post("/api/shops/shop-1/stop")
    assert stop_success.json() == {"code": 0, "msg": "ok", "data": None}

    stop_failure = client.post("/api/shops/missing/stop")
    assert stop_failure.json() == {"code": -1, "msg": "店铺未在运行", "data": None}

    running_response = client.get("/api/shops/running")
    assert running_response.json() == {"code": 0, "msg": "ok", "data": ["shop-1", "shop-2"]}
