from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import settings as settings_api
from backend.api import shops as shops_api
from backend.db import database
from backend.main import app


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


def _seed_backend_data() -> None:
    with database.get_db() as conn:
        conn.execute(
            (
                "INSERT INTO shops (id, name, platform, username, password, is_online, ai_enabled, cookie_valid) "
                "VALUES (?,?,?,?,?,?,?,?)"
            ),
            ("shop-1", "拼多多店铺", "pdd", "seller1", "secret1", 0, 0, 1),
        )
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, is_online, ai_enabled) VALUES (?,?,?,?,?,?,?)",
            ("shop-2", "抖店店铺", "douyin", "seller2", "secret2", 1, 1),
        )
        conn.execute(
            (
                "INSERT INTO shop_configs (shop_id, llm_mode, custom_api_key, custom_model, reply_style_note, "
                "knowledge_paths, use_global_knowledge, human_agent_name, escalation_rules, escalation_fallback_msg) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)"
            ),
            (
                "shop-1",
                "custom",
                "sk-demo",
                "gpt-test",
                "简洁专业",
                '["global/refund.md"]',
                1,
                "人工客服A",
                '[{"id":"rule-1","type":"keyword","value":"退款"}]',
                "稍后转人工",
            ),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name, status, "
                "last_message_preview, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))"
            ),
            ("session-1", "shop-1", "拼多多店铺", "pdd", "buyer-1", "买家甲", "ai_processing", "收到"),
        )
        conn.execute(
            (
                "INSERT INTO sessions (id, shop_id, shop_name, platform, buyer_id, buyer_name, status, "
                "last_message_preview, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))"
            ),
            ("session-2", "shop-2", "抖店店铺", "douyin", "buyer-2", "买家乙", "ai_processing", "在吗"),
        )
        conn.execute(
            (
                "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) "
                "VALUES (?, ?, ?, ?, datetime('now','localtime','-2 minutes'), ?)"
            ),
            ("msg-1", "session-1", "buyer", "你好", "session-1:buyer:1"),
        )
        conn.execute(
            (
                "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) "
                "VALUES (?, ?, ?, ?, datetime('now','localtime','-1 minutes'), ?)"
            ),
            ("msg-2", "session-1", "ai", "您好，请问有什么可以帮您", "session-1:ai:1"),
        )
        conn.execute(
            (
                "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) "
                "VALUES (?, ?, ?, ?, datetime('now','localtime','-30 seconds'), ?)"
            ),
            ("msg-3", "session-2", "buyer", "在吗", "session-2:buyer:1"),
        )
        conn.execute(
            (
                "INSERT INTO escalation_logs (id, session_id, shop_id, trigger_rule_type, trigger_rule_value) "
                "VALUES (?, ?, ?, ?, ?)"
            ),
            ("esc-1", "session-2", "shop-2", "keyword", "退款"),
        )
        conn.execute(
            (
                "INSERT INTO knowledge_files (id, name, path, node_type, parent_path, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?)"
            ),
            ("node-root", "global", "global", "folder", None, 0),
        )
        conn.execute(
            (
                "INSERT INTO knowledge_files (id, name, path, node_type, parent_path, content, sort_order) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)"
            ),
            ("node-file", "refund.md", "global/refund.md", "file", "global", "退款说明", 1),
        )


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "api.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    _seed_backend_data()

    with TestClient(app) as test_client:
        yield test_client

    _cleanup_database_files(db_path)


def test_shop_endpoints_cover_listing_updates_and_missing_shop(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_calls: list[str] = []
    stop_calls: list[str] = []

    async def fake_start_shop(shop_id: str) -> bool:
        start_calls.append(shop_id)
        return True

    async def fake_stop_shop(shop_id: str) -> bool:
        stop_calls.append(shop_id)
        return True

    monkeypatch.setattr(shops_api, "start_shop", fake_start_shop)
    monkeypatch.setattr(shops_api, "stop_shop", fake_stop_shop)
    monkeypatch.setattr(shops_api, "get_running_shops", lambda: ["shop-1"])

    list_response = client.get("/api/shops")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload["code"] == 0
    assert payload["msg"] == "ok"
    assert {item["id"] for item in payload["data"]} == {"shop-1", "shop-2"}

    toggle_ai_response = client.patch("/api/shops/shop-1/ai", json={"enabled": True})
    assert toggle_ai_response.json()["data"]["aiEnabled"] is True

    toggle_online_response = client.post("/api/shops/shop-1/toggle")
    assert toggle_online_response.json()["data"]["isOnline"] is True
    assert start_calls == ["shop-1"]
    with database.get_db() as conn:
        online_row = conn.execute("SELECT is_online FROM shops WHERE id=?", ("shop-1",)).fetchone()
    assert online_row is not None
    assert online_row["is_online"] == 1

    toggle_offline_response = client.post("/api/shops/shop-1/toggle")
    assert toggle_offline_response.json()["data"]["isOnline"] is False
    assert stop_calls == ["shop-1"]
    with database.get_db() as conn:
        offline_row = conn.execute("SELECT is_online FROM shops WHERE id=?", ("shop-1",)).fetchone()
    assert offline_row is not None
    assert offline_row["is_online"] == 0

    open_browser_response = client.post("/api/shops/shop-1/open-browser")
    assert open_browser_response.json() == {"code": 0, "msg": "ok", "data": None}
    with database.get_db() as conn:
        reopened_row = conn.execute("SELECT is_online FROM shops WHERE id=?", ("shop-1",)).fetchone()
    assert reopened_row is not None
    assert reopened_row["is_online"] == 1

    default_config_response = client.get("/api/shops/shop-2/config")
    default_config = default_config_response.json()["data"]
    assert default_config["shopId"] == "shop-2"
    assert default_config["knowledgePaths"] == []
    assert default_config["llmMode"] == "global"

    save_config_response = client.put(
        "/api/shops/shop-2/config",
        json={
            "shopId": "shop-2",
            "name": "抖店店铺-已更新",
            "username": "new-user",
            "password": "new-pass",
            "platform": "douyin",
            "cookieValid": True,
            "cookieLastRefresh": "",
            "aiEnabled": False,
            "llmMode": "custom",
            "customApiKey": "sk-live",
            "customModel": "gpt-5-mini",
            "replyStyleNote": "更热情",
            "knowledgePaths": ["global/refund.md"],
            "useGlobalKnowledge": False,
            "humanAgentName": "人工客服B",
            "escalationRules": [{"id": "rule-2", "type": "regex", "value": "退款"}],
            "escalationFallbackMsg": "稍后为您转人工",
        },
    )
    saved_config = save_config_response.json()["data"]
    assert saved_config["name"] == "抖店店铺-已更新"
    assert saved_config["customModel"] == "gpt-5-mini"
    assert saved_config["useGlobalKnowledge"] is False

    missing_shop_response = client.get("/api/shops/missing/config")
    assert missing_shop_response.json() == {"code": -1, "msg": "店铺不存在", "data": None}


def test_dashboard_chat_knowledge_and_settings_endpoints_cover_normal_and_error_paths(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dashboard_response = client.get("/api/dashboard/summary")
    dashboard_payload = dashboard_response.json()
    assert dashboard_payload["code"] == 0
    assert dashboard_payload["data"]["todayServedCount"] == 2
    assert dashboard_payload["data"]["aiReplyRate"] == 1.0
    assert dashboard_payload["data"]["escalationCount"] == 1
    assert dashboard_payload["data"]["unrepliedCount"] == 1

    sessions_response = client.get("/api/chat/sessions")
    sessions_payload = sessions_response.json()["data"]
    assert {session["id"] for session in sessions_payload} == {"session-1", "session-2"}
    target_session = next(session for session in sessions_payload if session["id"] == "session-1")
    assert [message["sender"] for message in target_session["messages"]] == ["buyer", "ai"]

    takeover_response = client.post("/api/chat/sessions/session-2/takeover")
    assert takeover_response.json()["data"]["status"] == "escalated"
    missing_takeover_response = client.post("/api/chat/sessions/missing/takeover")
    assert missing_takeover_response.json() == {"code": -1, "msg": "会话不存在", "data": None}

    tree_response = client.get("/api/knowledge/tree")
    tree_payload = tree_response.json()["data"]
    assert tree_payload[0]["nodeType"] == "folder"
    assert tree_payload[0]["children"][0]["path"] == "global/refund.md"

    file_list_response = client.get("/api/knowledge/files")
    assert file_list_response.json()["data"] == ["global/refund.md"]

    document_response = client.get("/api/knowledge/document", params={"path": "global/refund.md"})
    assert document_response.json()["data"]["content"] == "退款说明"

    save_document_response = client.put(
        "/api/knowledge/document",
        json={"path": "global/refund.md", "content": "已更新内容"},
    )
    assert save_document_response.json()["data"]["content"] == "已更新内容"

    create_document_response = client.post(
        "/api/knowledge/document",
        json={"parentPath": "global", "name": "faq.md"},
    )
    assert create_document_response.json()["data"]["path"] == "global/faq.md"

    delete_document_response = client.request(
        "DELETE",
        "/api/knowledge/document",
        json={"path": "global/faq.md"},
    )
    assert delete_document_response.json()["data"] == {"path": "global/faq.md"}

    missing_document_response = client.get("/api/knowledge/document", params={"path": "missing.md"})
    assert missing_document_response.json() == {"code": -1, "msg": "文件不存在", "data": None}

    missing_delete_response = client.request(
        "DELETE",
        "/api/knowledge/document",
        json={"path": "missing.md"},
    )
    assert missing_delete_response.json() == {"code": -1, "msg": "文件不存在", "data": None}

    settings_response = client.get("/api/settings")
    settings_payload = settings_response.json()["data"]
    assert settings_payload["temperature"] == 0.7
    assert settings_payload["defaultKeywords"] == []
    assert settings_payload["notifyWebhookType"] == "feishu"

    save_settings_response = client.put(
        "/api/settings",
        json={
            "apiBaseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-test",
            "defaultModel": "gpt-5-mini",
            "temperature": 0.2,
            "maxTokens": 512,
            "defaultFallbackMsg": "稍等",
            "defaultKeywords": ["退款", "售后"],
            "logLevel": "DEBUG",
            "historyRetentionDays": 15,
            "notifyWebhookUrl": "https://example.com/webhook",
            "notifyWebhookType": "wecom",
            "maxShops": 20,
        },
    )
    saved_settings = save_settings_response.json()["data"]
    assert saved_settings["defaultKeywords"] == ["退款", "售后"]
    assert saved_settings["maxTokens"] == 512
    assert saved_settings["temperature"] == 0.2
    assert saved_settings["notifyWebhookUrl"] == "https://example.com/webhook"
    assert saved_settings["notifyWebhookType"] == "wecom"

    test_llm_success = client.post(
        "/api/settings/test-llm",
        json={"apiBaseUrl": "https://api.openai.com", "apiKey": "sk-test", "model": "gpt-5-mini"},
    )
    assert test_llm_success.json()["data"]["ok"] is True

    test_llm_failure = client.post(
        "/api/settings/test-llm",
        json={"apiBaseUrl": "https://api.openai.com", "apiKey": "sk-test", "model": ""},
    )
    assert test_llm_failure.json()["data"] == {"ok": False, "message": "参数不完整"}

    webhook_calls: list[dict[str, str]] = []

    async def fake_send_notification(
        title: str,
        content: str,
        level: str = "warning",
        *,
        url: str | None = None,
        webhook_type: str | None = None,
        event_key: str | None = None,
        dedupe: bool = True,
    ) -> bool:
        webhook_calls.append(
            {
                "title": title,
                "content": content,
                "level": level,
                "url": url or "",
                "webhook_type": webhook_type or "",
                "event_key": event_key or "",
                "dedupe": str(dedupe),
            }
        )
        return True

    monkeypatch.setattr(settings_api, "send_notification", fake_send_notification)
    test_webhook_success = client.post(
        "/api/settings/test-webhook",
        json={"url": "https://example.com/hooks/test", "webhookType": "dingtalk"},
    )
    assert test_webhook_success.json()["data"] == {"ok": True, "message": "发送成功"}
    assert webhook_calls == [
        {
            "title": "PDDCS 通知测试",
            "content": "这是一条来自系统设置页的测试通知。",
            "level": "info",
            "url": "https://example.com/hooks/test",
            "webhook_type": "dingtalk",
            "event_key": "",
            "dedupe": "False",
        }
    ]

    async def fake_failed_notification(
        title: str,
        content: str,
        level: str = "warning",
        *,
        url: str | None = None,
        webhook_type: str | None = None,
        event_key: str | None = None,
        dedupe: bool = True,
    ) -> bool:
        del title, content, level, url, webhook_type, event_key, dedupe
        return False

    monkeypatch.setattr(settings_api, "send_notification", fake_failed_notification)
    test_webhook_failure = client.post(
        "/api/settings/test-webhook",
        json={"url": "https://example.com/hooks/test", "webhookType": "generic"},
    )
    assert test_webhook_failure.json()["data"] == {
        "ok": False,
        "message": "发送失败，请检查 Webhook URL 或网络状态",
    }
