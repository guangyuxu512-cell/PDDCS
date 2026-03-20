from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from backend.adapters.base import RawMessage
from backend.db import database
from backend.services.message_processor import process_buyer_message


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


def _seed_shop(escalation_rules: list[dict[str, str]] | None = None) -> None:
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, ai_enabled) VALUES (?,?,?,?,?,?)",
            ("shop-1", "测试店铺", "pdd", "seller", "secret", 1),
        )
        conn.execute(
            """
            INSERT INTO shop_configs (
                shop_id,
                llm_mode,
                reply_style_note,
                knowledge_paths,
                use_global_knowledge,
                human_agent_name,
                escalation_rules,
                escalation_fallback_msg
            ) VALUES (?,?,?,?,?,?,?,?)
            """,
            (
                "shop-1",
                "global",
                "友好一点",
                json.dumps(["global/refund.md"], ensure_ascii=False),
                1,
                "客服A",
                json.dumps(escalation_rules or [], ensure_ascii=False),
                "请稍等，马上为您处理~",
            ),
        )
        conn.execute(
            """
            INSERT INTO knowledge_files (id, name, path, node_type, parent_path, content, sort_order)
            VALUES (?,?,?,?,?,?,?)
            """,
            ("file-1", "refund.md", "global/refund.md", "file", "global", "退款说明内容", 1),
        )


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "message-processor.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    yield db_path
    _cleanup_database_files(db_path)


class _FakeLlmClient:
    def __init__(self, reply_text: str) -> None:
        self.reply_text = reply_text
        self.calls: list[dict[str, object]] = []

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        fallback: str = "",
    ) -> str:
        self.calls.append(
            {
                "messages": messages,
                "system_prompt": system_prompt,
                "fallback": fallback,
            }
        )
        return self.reply_text


class _NeverCalledLlmClient:
    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        fallback: str = "",
    ) -> str:
        del messages, system_prompt, fallback
        raise AssertionError("LLM should not be called when escalation is triggered")


@pytest.mark.asyncio
async def test_process_buyer_message_saves_session_and_ai_reply(isolated_database: Path) -> None:
    del isolated_database
    _seed_shop()
    fake_llm = _FakeLlmClient("您好，这边已经为您处理")
    raw_message = RawMessage(
        session_id="buyer-1",
        buyer_id="buyer-1",
        buyer_name="买家甲",
        content="你好，我想咨询退款",
        sender="buyer",
        timestamp="2026-03-20T10:00:00",
        dedup_key="dedup-1",
    )

    result = await process_buyer_message("shop-1", raw_message, fake_llm)  # type: ignore[arg-type]
    assert result.action == "reply"
    assert result.reply_text == "您好，这边已经为您处理"
    assert fake_llm.calls
    assert "退款说明内容" in str(fake_llm.calls[0]["system_prompt"])

    with database.get_db() as conn:
        session_row = conn.execute("SELECT * FROM sessions WHERE id=?", (result.session_id,)).fetchone()
        message_rows = conn.execute(
            "SELECT sender, content FROM messages WHERE session_id=?",
            (result.session_id,),
        ).fetchall()

    assert session_row is not None
    assert session_row["status"] == "ai_processing"
    assert {(row["sender"], row["content"]) for row in message_rows} == {
        ("buyer", "你好，我想咨询退款"),
        ("ai", "您好，这边已经为您处理"),
    }


@pytest.mark.asyncio
async def test_process_buyer_message_returns_skip_for_duplicate_message(isolated_database: Path) -> None:
    del isolated_database
    _seed_shop()
    fake_llm = _FakeLlmClient("已回复")
    raw_message = RawMessage(
        session_id="buyer-2",
        buyer_id="buyer-2",
        buyer_name="买家乙",
        content="在吗",
        sender="buyer",
        timestamp="2026-03-20T10:05:00",
        dedup_key="dedup-duplicate",
    )

    first_result = await process_buyer_message("shop-1", raw_message, fake_llm)  # type: ignore[arg-type]
    second_result = await process_buyer_message("shop-1", raw_message, fake_llm)  # type: ignore[arg-type]

    with database.get_db() as conn:
        message_count = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=?",
            (first_result.session_id,),
        ).fetchone()[0]

    assert first_result.action == "reply"
    assert second_result.action == "skip"
    assert message_count == 2


@pytest.mark.asyncio
async def test_process_buyer_message_triggers_escalation_without_calling_llm(isolated_database: Path) -> None:
    del isolated_database
    _seed_shop(escalation_rules=[{"type": "keyword", "value": "退款"}])
    raw_message = RawMessage(
        session_id="buyer-3",
        buyer_id="buyer-3",
        buyer_name="买家丙",
        content="我要退款",
        sender="buyer",
        timestamp="2026-03-20T10:10:00",
        dedup_key="dedup-escalate",
    )

    result = await process_buyer_message("shop-1", raw_message, _NeverCalledLlmClient())  # type: ignore[arg-type]
    assert result.action == "escalate"
    assert result.escalation is not None
    assert result.escalation.rule_type == "keyword"

    with database.get_db() as conn:
        session_row = conn.execute("SELECT status FROM sessions WHERE id=?", (result.session_id,)).fetchone()
        message_rows = conn.execute(
            "SELECT sender, content FROM messages WHERE session_id=? ORDER BY created_at ASC",
            (result.session_id,),
        ).fetchall()
        escalation_row = conn.execute(
            "SELECT trigger_rule_type, target_agent, success FROM escalation_logs WHERE session_id=?",
            (result.session_id,),
        ).fetchone()

    assert session_row is not None
    assert session_row["status"] == "escalated"
    assert [(row["sender"], row["content"]) for row in message_rows] == [("buyer", "我要退款")]
    assert escalation_row is not None
    assert escalation_row["trigger_rule_type"] == "keyword"
    assert escalation_row["target_agent"] == "客服A"
    assert escalation_row["success"] == 0
