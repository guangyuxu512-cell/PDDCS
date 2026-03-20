from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.db import database
from backend.main import app


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "dashboard-route.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()

    with TestClient(app) as test_client:
        yield test_client

    _cleanup_database_files(db_path)


def test_dashboard_primary_route_returns_same_payload_as_compatibility_route(client: TestClient) -> None:
    primary_response = client.get("/api/dashboard")
    compatibility_response = client.get("/api/dashboard/summary")

    assert primary_response.status_code == 200
    assert primary_response.json() == compatibility_response.json()
