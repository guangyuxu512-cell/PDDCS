from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from pydantic import ValidationError

from backend.db import database
from backend.db.models import ChatMessage, ChatSession, Shop, ShopConfig, SystemSettings


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_dir = tmp_path / "data"
    db_path = db_dir / "test.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    yield db_path
    _cleanup_database_files(db_path)


def test_database_schema_and_models_align_with_frontend_types(isolated_database: Path) -> None:
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, is_online) VALUES (?,?,?,?,?,?)",
            ("shop-1", "测试店铺", "pdd", "test_user", "test_pass", 1),
        )
        conn.execute(
            (
                "INSERT INTO shop_configs (shop_id, knowledge_paths, escalation_rules, human_agent_name) "
                "VALUES (?,?,?,?)"
            ),
            (
                "shop-1",
                json.dumps(["退款话术.md"], ensure_ascii=False),
                json.dumps([{"id": "rule-1", "type": "keyword", "value": "退款"}], ensure_ascii=False),
                "客服小王",
            ),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name, "
                "last_message_preview) VALUES (?,?,?,?,?,?,?)"
            ),
            ("session-1", "shop-1", "测试店铺", "pdd", "buyer-1", "买家A", "你好，我要退款"),
        )
        conn.execute(
            "INSERT INTO messages (id, session_id, sender, content, dedup_key) VALUES (?,?,?,?,?)",
            ("message-1", "session-1", "buyer", "你好，我要退款", "session-1:1:abc123"),
        )

        shop_row = conn.execute("SELECT * FROM shops WHERE id='shop-1'").fetchone()
        session_row = conn.execute("SELECT * FROM sessions WHERE id='session-1'").fetchone()
        message_row = conn.execute("SELECT * FROM messages WHERE id='message-1'").fetchone()
        config_row = conn.execute(
            (
                "SELECT s.name, s.username, s.password, s.platform, s.cookie_valid, "
                "s.cookie_last_refresh, s.ai_enabled, c.* "
                "FROM shop_configs c JOIN shops s ON s.id = c.shop_id WHERE c.shop_id='shop-1'"
            )
        ).fetchone()
        settings_rows = conn.execute("SELECT key, value FROM system_settings").fetchall()

    assert shop_row is not None
    assert session_row is not None
    assert message_row is not None
    assert config_row is not None

    shop = Shop.model_validate(dict(shop_row))
    config = ShopConfig.model_validate(dict(config_row))
    message = ChatMessage.model_validate(dict(message_row))
    session = ChatSession.model_validate({**dict(session_row), "messages": [dict(message_row)]})
    settings = SystemSettings.model_validate({row["key"]: row["value"] for row in settings_rows})

    assert shop.model_dump()["isOnline"] is True
    assert config.model_dump()["knowledgePaths"] == ["退款话术.md"]
    assert config.model_dump()["escalationRules"][0]["value"] == "退款"
    assert message.model_dump()["createdAt"]
    assert session.model_dump()["buyerId"] == "buyer-1"
    assert session.model_dump()["messages"][0]["sender"] == "buyer"
    assert settings.model_dump()["defaultKeywords"] == []
    assert settings.model_dump()["maxTokens"] == 200
    assert isolated_database.exists()


def test_get_db_rolls_back_when_statement_fails(isolated_database: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        with database.get_db() as conn:
            conn.execute(
                "INSERT INTO shops (id, name, platform) VALUES (?,?,?)",
                ("shop-rollback", "回滚店铺", "pdd"),
            )
            conn.execute(
                "INSERT INTO shops (id, name, platform) VALUES (?,?,?)",
                ("shop-rollback", "重复店铺", "pdd"),
            )

    with closing(database.get_connection()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM shops WHERE id='shop-rollback'").fetchone()[0]

    assert count == 0


def test_shop_config_rejects_invalid_json_payload() -> None:
    with pytest.raises(ValidationError):
        ShopConfig.model_validate(
            {
                "shop_id": "shop-invalid",
                "name": "异常店铺",
                "platform": "pdd",
                "knowledge_paths": "[",
            }
        )
