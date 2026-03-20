"""单条消息处理链。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, TypeVar

from backend.adapters.base import RawMessage
from backend.ai.llm_client import DEFAULT_FALLBACK, LlmClient
from backend.db.database import get_db
from backend.services.escalation_checker import EscalationResult, check_escalation


logger = logging.getLogger(__name__)

DEFAULT_LLM_CALL_TIMEOUT_SECONDS = 40.0
T = TypeVar("T")


def _iso_now() -> str:
    return datetime.now().isoformat()


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float env %s=%r, using default %s", name, value, default)
        return default


async def _wait(awaitable: Awaitable[T], timeout_seconds: float) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _parse_json_field(raw_value: Any, default: Any) -> Any:
    if raw_value in (None, ""):
        return default
    if isinstance(raw_value, str):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON field %r, using default", raw_value)
            return default
    return raw_value


@dataclass(slots=True)
class ProcessResult:
    """消息处理结果。"""

    action: str
    session_id: str
    reply_text: str = ""
    escalation: EscalationResult | None = None
    message_id: str = ""


def _get_or_create_session(conn: Any, shop_id: str, message: RawMessage) -> str:
    row = conn.execute(
        "SELECT id FROM sessions WHERE shop_id=? AND buyer_id=? ORDER BY updated_at DESC LIMIT 1",
        (shop_id, message.buyer_id),
    ).fetchone()
    if row is not None:
        return str(row["id"])

    shop_row = conn.execute("SELECT name, platform FROM shops WHERE id=?", (shop_id,)).fetchone()
    if shop_row is None:
        raise ValueError(f"店铺不存在: {shop_id}")

    session_id = str(uuid.uuid4())
    now = message.timestamp or _iso_now()
    conn.execute(
        """
        INSERT INTO sessions (
            id,
            shop_id,
            shop_name,
            platform,
            buyer_id,
            buyer_name,
            status,
            last_message_preview,
            updated_at,
            created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            shop_id,
            shop_row["name"],
            shop_row["platform"],
            message.buyer_id,
            message.buyer_name,
            "ai_processing",
            message.content[:100],
            now,
            now,
        ),
    )
    return session_id


def _save_message(conn: Any, session_id: str, message: RawMessage) -> str | None:
    existing = conn.execute(
        "SELECT id FROM messages WHERE dedup_key=?",
        (message.dedup_key,),
    ).fetchone()
    if existing is not None:
        return None

    message_id = str(uuid.uuid4())
    created_at = message.timestamp or _iso_now()
    conn.execute(
        "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) VALUES (?,?,?,?,?,?)",
        (message_id, session_id, message.sender, message.content, created_at, message.dedup_key),
    )
    conn.execute(
        "UPDATE sessions SET last_message_preview=?, updated_at=? WHERE id=?",
        (message.content[:100], created_at, session_id),
    )
    return message_id


def _get_recent_messages(conn: Any, session_id: str, limit: int = 20) -> list[dict[str, str]]:
    rows = conn.execute(
        """
        SELECT sender, content
        FROM messages
        WHERE session_id=?
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (session_id, limit),
    ).fetchall()
    return [{"sender": row["sender"], "content": row["content"]} for row in reversed(rows)]


def _get_shop_config(conn: Any, shop_id: str) -> dict[str, Any]:
    defaults: dict[str, Any] = {
        "llm_mode": "global",
        "custom_api_key": "",
        "custom_model": "",
        "reply_style_note": "",
        "knowledge_paths": [],
        "use_global_knowledge": True,
        "human_agent_name": "",
        "escalation_rules": [],
        "escalation_fallback_msg": "",
    }

    row = conn.execute("SELECT * FROM shop_configs WHERE shop_id=?", (shop_id,)).fetchone()
    if row is None:
        return defaults

    data = dict(row)
    data["knowledge_paths"] = _parse_json_field(data.get("knowledge_paths"), [])
    data["escalation_rules"] = _parse_json_field(data.get("escalation_rules"), [])
    return {**defaults, **data}


def _get_knowledge_content(conn: Any, paths: list[str]) -> str:
    normalized_paths = list(dict.fromkeys(path for path in paths if path))
    if not normalized_paths:
        return ""

    placeholders = ",".join("?" for _ in normalized_paths)
    rows = conn.execute(
        f"""
        SELECT path, content
        FROM knowledge_files
        WHERE path IN ({placeholders}) AND node_type='file'
        ORDER BY sort_order ASC, path ASC
        """,
        normalized_paths,
    ).fetchall()
    parts = [f"--- {row['path']} ---\n{row['content']}" for row in rows if str(row["content"]).strip()]
    return "\n\n".join(parts)


def _build_system_prompt(shop_config: dict[str, Any], knowledge_content: str) -> str:
    parts = [
        "你是一个电商客服AI助手。",
        "请根据以下知识库内容和对话历史回复买家问题。",
        "要求：语气亲切自然，不要暴露自己是AI。",
        "回复保持简短，一般控制在1到3句话。",
    ]

    style_note = str(shop_config.get("reply_style_note", "")).strip()
    if style_note:
        parts.append(f"回复风格要求：{style_note}")

    if knowledge_content:
        parts.append("以下是参考知识库：")
        parts.append(knowledge_content)

    return "\n".join(parts)


def _build_chat_messages(recent_messages: list[dict[str, str]]) -> list[dict[str, str]]:
    chat_messages: list[dict[str, str]] = []
    for message in recent_messages:
        role = "user" if message["sender"] == "buyer" else "assistant"
        chat_messages.append({"role": role, "content": message["content"]})
    return chat_messages


async def process_buyer_message(
    shop_id: str,
    raw_msg: RawMessage,
    llm_client: LlmClient,
) -> ProcessResult:
    """处理一条买家消息。"""
    with get_db() as conn:
        session_id = _get_or_create_session(conn, shop_id, raw_msg)
        message_id = _save_message(conn, session_id, raw_msg)
        if message_id is None:
            return ProcessResult(action="skip", session_id=session_id)

        shop_config = _get_shop_config(conn, shop_id)
        recent_messages = _get_recent_messages(conn, session_id, limit=20)
        escalation_result = check_escalation(
            message_content=raw_msg.content,
            rules=shop_config.get("escalation_rules", []),
            recent_messages=recent_messages[:-1],
        )
        if escalation_result.should_escalate:
            now = raw_msg.timestamp or _iso_now()
            conn.execute(
                "UPDATE sessions SET status='escalated', updated_at=? WHERE id=?",
                (now, session_id),
            )
            conn.execute(
                """
                INSERT INTO escalation_logs (
                    id,
                    session_id,
                    shop_id,
                    trigger_rule_type,
                    trigger_rule_value,
                    matched_content,
                    target_agent,
                    success,
                    created_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    shop_id,
                    escalation_result.rule_type,
                    escalation_result.rule_value,
                    escalation_result.matched_content,
                    str(shop_config.get("human_agent_name", "")),
                    0,
                    now,
                ),
            )
            conn.execute(
                "UPDATE shops SET last_active_at=?, updated_at=? WHERE id=?",
                (now, now, shop_id),
            )
            return ProcessResult(
                action="escalate",
                session_id=session_id,
                escalation=escalation_result,
                message_id=message_id,
            )

        configured_paths = list(shop_config.get("knowledge_paths", []))
        if bool(shop_config.get("use_global_knowledge", True)):
            rows = conn.execute(
                "SELECT path FROM knowledge_files WHERE node_type='file' ORDER BY sort_order ASC, path ASC"
            ).fetchall()
            knowledge_paths = configured_paths + [row["path"] for row in rows]
        else:
            knowledge_paths = configured_paths

        knowledge_content = _get_knowledge_content(conn, knowledge_paths)
        system_prompt = _build_system_prompt(shop_config, knowledge_content)
        chat_messages = _build_chat_messages(recent_messages)
        fallback = str(shop_config.get("escalation_fallback_msg", "")).strip() or DEFAULT_FALLBACK

    try:
        reply_text = await _wait(
            llm_client.chat(
                messages=chat_messages,
                system_prompt=system_prompt,
                fallback=fallback,
            ),
            timeout_seconds=_env_float("MESSAGE_PROCESSOR_LLM_TIMEOUT_SECONDS", DEFAULT_LLM_CALL_TIMEOUT_SECONDS),
        )
    except Exception:
        logger.exception("Failed to generate LLM reply for shop %s session %s", shop_id, session_id)
        reply_text = fallback

    with get_db() as conn:
        now = _iso_now()
        ai_message_id = str(uuid.uuid4())
        ai_dedup_key = f"{shop_id}:{session_id}:ai:{ai_message_id}"
        conn.execute(
            "INSERT INTO messages (id, session_id, sender, content, created_at, dedup_key) VALUES (?,?,?,?,?,?)",
            (ai_message_id, session_id, "ai", reply_text, now, ai_dedup_key),
        )
        conn.execute(
            "UPDATE sessions SET status='ai_processing', last_message_preview=?, updated_at=? WHERE id=?",
            (reply_text[:100], now, session_id),
        )
        conn.execute(
            "UPDATE shops SET last_active_at=?, updated_at=? WHERE id=?",
            (now, now, shop_id),
        )

    return ProcessResult(
        action="reply",
        session_id=session_id,
        reply_text=reply_text,
        message_id=message_id,
    )
