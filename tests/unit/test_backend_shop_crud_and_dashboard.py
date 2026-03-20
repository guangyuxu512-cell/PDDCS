from __future__ import annotations

from collections.abc import Iterator
from contextlib import closing
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
    db_path = db_dir / "crud.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()

    with TestClient(app) as test_client:
        yield test_client

    _cleanup_database_files(db_path)


def test_dashboard_summary_counts_all_seeded_records_without_date_filter(client: TestClient) -> None:
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password) VALUES (?,?,?,?,?)",
            ("shop-a", "老数据店铺", "pdd", "old-user", "secret"),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name, status, "
                "last_message_preview, updated_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
            ),
            (
                "session-1",
                "shop-a",
                "老数据店铺",
                "pdd",
                "buyer-1",
                "买家甲",
                "ai_processing",
                "仍未回复",
                "2024-01-01T12:10:00",
                "2024-01-01T12:00:00",
            ),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name, status, "
                "last_message_preview, updated_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)"
            ),
            (
                "session-2",
                "shop-a",
                "老数据店铺",
                "pdd",
                "buyer-2",
                "买家乙",
                "closed",
                "已回复",
                "2024-01-01T13:10:00",
                "2024-01-01T13:00:00",
            ),
        )
        conn.execute(
            (
                "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) VALUES "
                "(?,?,?,?,?,?), (?,?,?,?,?,?), (?,?,?,?,?,?)"
            ),
            (
                "message-1",
                "session-1",
                "buyer",
                "还没发货",
                "2024-01-01T12:01:00",
                "session-1:1",
                "message-2",
                "session-2",
                "buyer",
                "发货了吗",
                "2024-01-01T13:01:00",
                "session-2:1",
                "message-3",
                "session-2",
                "ai",
                "已经发货了",
                "2024-01-01T13:02:00",
                "session-2:2",
            ),
        )
        conn.execute(
            (
                "INSERT INTO escalation_logs (id, session_id, shop_id, trigger_rule_type, created_at) "
                "VALUES (?,?,?,?,?)"
            ),
            ("escalation-1", "session-1", "shop-a", "keyword", "2024-01-01T12:05:00"),
        )

    response = client.get("/api/dashboard/summary")
    payload = response.json()

    assert payload["code"] == 0
    assert payload["data"] == {
        "todayServedCount": 2,
        "aiReplyRate": 1.0,
        "escalationCount": 1,
        "avgFirstResponseMs": 0,
        "unrepliedCount": 1,
        "yesterdayServedCount": 0,
    }


def test_shop_create_delete_and_scan_endpoints_cover_normal_and_error_paths(client: TestClient) -> None:
    create_response = client.post(
        "/api/shops",
        json={
            "name": "新拼多多店铺",
            "platform": "pdd",
            "username": "pdd_new",
            "password": "123456",
        },
    )
    created_shop = create_response.json()["data"]

    assert create_response.status_code == 200
    assert created_shop["name"] == "新拼多多店铺"
    assert created_shop["platform"] == "pdd"
    assert created_shop["isOnline"] is False
    assert created_shop["aiEnabled"] is False

    with database.get_db() as conn:
        config_row = conn.execute(
            "SELECT shop_id FROM shop_configs WHERE shop_id=?",
            (created_shop["id"],),
        ).fetchone()
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name, updated_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)"
            ),
            (
                "cascade-session",
                created_shop["id"],
                "新拼多多店铺",
                "pdd",
                "buyer-cascade",
                "买家丙",
                "2024-01-01T10:00:00",
                "2024-01-01T10:00:00",
            ),
        )
        conn.execute(
            "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) VALUES (?,?,?,?,?,?)",
            ("cascade-message", "cascade-session", "buyer", "测试消息", "2024-01-01T10:01:00", "cascade:1"),
        )

    assert config_row is not None

    scan_response = client.post("/api/shops/scan")
    assert scan_response.json() == {"code": 0, "msg": "ok", "data": []}

    delete_response = client.delete(f"/api/shops/{created_shop['id']}")
    assert delete_response.json() == {"code": 0, "msg": "ok", "data": None}

    missing_delete_response = client.delete("/api/shops/missing-shop")
    assert missing_delete_response.json() == {"code": -1, "msg": "店铺不存在", "data": None}

    with closing(database.get_connection()) as conn:
        shop_count = conn.execute(
            "SELECT COUNT(*) FROM shops WHERE id=?",
            (created_shop["id"],),
        ).fetchone()[0]
        config_count = conn.execute(
            "SELECT COUNT(*) FROM shop_configs WHERE shop_id=?",
            (created_shop["id"],),
        ).fetchone()[0]
        session_count = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE shop_id=?",
            (created_shop["id"],),
        ).fetchone()[0]
        message_count = conn.execute(
            (
                "SELECT COUNT(*) FROM messages WHERE session_id IN "
                "(SELECT id FROM sessions WHERE shop_id=?)"
            ),
            (created_shop["id"],),
        ).fetchone()[0]

    assert shop_count == 0
    assert config_count == 0
    assert session_count == 0
    assert message_count == 0
