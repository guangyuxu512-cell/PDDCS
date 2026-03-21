"""验证脚本：建表、插入测试数据并校验模型映射。"""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

from backend.db.database import DB_PATH, get_db, init_database
from backend.db.models import ChatMessage, Shop, ShopConfig, SystemSettings


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


def _cleanup_database_files() -> None:
    for path in (
        DB_PATH,
        Path(f"{DB_PATH}-shm"),
        Path(f"{DB_PATH}-wal"),
    ):
        path.unlink(missing_ok=True)


def test() -> None:
    _cleanup_database_files()
    init_database()

    with get_db() as conn:
        shop_id = str(uuid.uuid4())
        session_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())

        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password) VALUES (?,?,?,?,?)",
            (shop_id, "测试店铺", "pdd", "test_user", "test_pass"),
        )
        conn.execute(
            (
                "INSERT INTO shop_configs (shop_id, knowledge_paths, escalation_rules, human_agent_name) "
                "VALUES (?,?,?,?)"
            ),
            (
                shop_id,
                '["退款话术.md"]',
                json.dumps([{"id": "r1", "type": "keyword", "value": "退款"}], ensure_ascii=False),
                "客服小王",
            ),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name) "
                "VALUES (?,?,?,?,?,?)"
            ),
            (session_id, shop_id, "测试店铺", "pdd", "buyer_001", "买家A"),
        )
        conn.execute(
            "INSERT INTO messages (id, session_id, sender, content, dedup_key) VALUES (?,?,?,?,?)",
            (message_id, session_id, "buyer", "你好，我要退款", f"{session_id}:1:abc123"),
        )

        shop_row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
        assert shop_row is not None
        shop = Shop.model_validate(dict(shop_row))
        assert shop.model_dump()["name"] == "测试店铺"
        assert shop.model_dump()["platform"] == "pdd"
        assert shop.model_dump()["isOnline"] is False

        config_row = conn.execute(
            (
                "SELECT s.name, s.username, s.password, s.platform, s.cookie_valid, "
                "s.cookie_last_refresh, s.ai_enabled, c.* "
                "FROM shop_configs c JOIN shops s ON s.id = c.shop_id WHERE c.shop_id=?"
            ),
            (shop_id,),
        ).fetchone()
        assert config_row is not None
        config = ShopConfig.model_validate(dict(config_row))
        assert config.model_dump()["knowledgePaths"] == ["退款话术.md"]
        assert config.model_dump()["escalationRules"][0]["type"] == "keyword"
        assert config.model_dump()["humanAgentName"] == "客服小王"

        message_row = conn.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        assert message_row is not None
        message = ChatMessage.model_validate(dict(message_row))
        assert message.model_dump()["sender"] == "buyer"
        assert message.model_dump()["content"] == "你好，我要退款"

        settings_rows = conn.execute("SELECT key, value FROM system_settings").fetchall()
        settings_dict = {row["key"]: row["value"] for row in settings_rows}
        settings = SystemSettings.model_validate(settings_dict)
        assert settings.model_dump()["temperature"] == 0.7
        assert settings.model_dump()["logLevel"] == "INFO"
        assert settings.model_dump()["notifyWebhookType"] == "feishu"
        assert settings.model_dump()["maxShops"] == 10

    _cleanup_database_files()
    print("✅ 全部验证通过：表结构 ↔ 前端类型完全对齐")


if __name__ == "__main__":
    test()
