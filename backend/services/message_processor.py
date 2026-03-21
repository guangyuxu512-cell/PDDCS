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

from sqlalchemy import select

from backend.adapters.base import RawMessage
from backend.ai.llm_client import DEFAULT_FALLBACK, LlmClient
from backend.db.database import get_sync_session
from backend.db.orm import EscalationLogTable, KnowledgeFileTable, MessageTable, SessionTable, ShopConfigTable, ShopTable
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
    action: str
    session_id: str
    reply_text: str = ""
    escalation: EscalationResult | None = None
    message_id: str = ""


def _get_or_create_session(shop_id: str, message: RawMessage) -> SessionTable:
    with get_sync_session() as session:
        row = session.scalar(
            select(SessionTable)
            .where(
                SessionTable.shop_id == shop_id,
                SessionTable.buyer_id == message.buyer_id,
            )
            .order_by(SessionTable.updated_at.desc())
        )
        if row is not None:
            return row

        shop_row = session.get(ShopTable, shop_id)
        if shop_row is None:
            raise ValueError(f"店铺不存在: {shop_id}")

        now = message.timestamp or _iso_now()
        row = SessionTable(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            shop_name=shop_row.name,
            platform=shop_row.platform,
            buyer_id=message.buyer_id,
            buyer_name=message.buyer_name,
            status="ai_processing",
            last_message_preview=message.content[:100],
            updated_at=now,
            created_at=now,
        )
        session.add(row)
        session.flush()
        session.refresh(row)
        return row


def _save_message(session_id: str, message: RawMessage) -> str | None:
    with get_sync_session() as session:
        existing = session.scalar(select(MessageTable.id).where(MessageTable.dedup_key == message.dedup_key))
        if existing is not None:
            return None

        created_at = message.timestamp or _iso_now()
        message_row = MessageTable(
            id=str(uuid.uuid4()),
            session_id=session_id,
            sender=message.sender,
            content=message.content,
            created_at=created_at,
            dedup_key=message.dedup_key,
        )
        session.add(message_row)

        session_row = session.get(SessionTable, session_id)
        if session_row is not None:
            session_row.last_message_preview = message.content[:100]
            session_row.updated_at = created_at

        session.flush()
        return message_row.id


def _get_recent_messages(session_id: str, limit: int = 20) -> list[dict[str, str]]:
    with get_sync_session() as session:
        rows = session.execute(
            select(MessageTable.sender, MessageTable.content)
            .where(MessageTable.session_id == session_id)
            .order_by(MessageTable.created_at.desc())
            .limit(limit)
        ).all()
    return [{"sender": row.sender, "content": row.content} for row in reversed(rows)]


def _get_shop_config(shop_id: str) -> dict[str, Any]:
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

    with get_sync_session() as session:
        row = session.get(ShopConfigTable, shop_id)
        if row is None:
            return defaults

        data = {
            "llm_mode": row.llm_mode,
            "custom_api_key": row.custom_api_key,
            "custom_model": row.custom_model,
            "reply_style_note": row.reply_style_note,
            "knowledge_paths": _parse_json_field(row.knowledge_paths, []),
            "use_global_knowledge": row.use_global_knowledge,
            "human_agent_name": row.human_agent_name,
            "escalation_rules": _parse_json_field(row.escalation_rules, []),
            "escalation_fallback_msg": row.escalation_fallback_msg,
        }
    return {**defaults, **data}


def _get_knowledge_content(paths: list[str]) -> str:
    normalized_paths = list(dict.fromkeys(path for path in paths if path))
    if not normalized_paths:
        return ""

    with get_sync_session() as session:
        rows = session.execute(
            select(KnowledgeFileTable.path, KnowledgeFileTable.content)
            .where(
                KnowledgeFileTable.path.in_(normalized_paths),
                KnowledgeFileTable.node_type == "file",
            )
            .order_by(KnowledgeFileTable.sort_order.asc(), KnowledgeFileTable.path.asc())
        ).all()

    parts = [f"--- {row.path} ---\n{row.content}" for row in rows if str(row.content).strip()]
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


def _mark_escalated(
    shop_id: str,
    session_id: str,
    escalation_result: EscalationResult,
    shop_config: dict[str, Any],
    timestamp: str,
) -> None:
    with get_sync_session() as session:
        session_row = session.get(SessionTable, session_id)
        shop_row = session.get(ShopTable, shop_id)
        if session_row is not None:
            session_row.status = "escalated"
            session_row.updated_at = timestamp
        if shop_row is not None:
            shop_row.last_active_at = timestamp
            shop_row.updated_at = timestamp

        session.add(
            EscalationLogTable(
                id=str(uuid.uuid4()),
                session_id=session_id,
                shop_id=shop_id,
                trigger_rule_type=escalation_result.rule_type,
                trigger_rule_value=escalation_result.rule_value,
                matched_content=escalation_result.matched_content,
                target_agent=str(shop_config.get("human_agent_name", "")),
                success=False,
                created_at=timestamp,
            )
        )


def _append_ai_reply(shop_id: str, session_id: str, reply_text: str) -> None:
    now = _iso_now()
    with get_sync_session() as session:
        ai_message_id = str(uuid.uuid4())
        ai_dedup_key = f"{shop_id}:{session_id}:ai:{ai_message_id}"
        session.add(
            MessageTable(
                id=ai_message_id,
                session_id=session_id,
                sender="ai",
                content=reply_text,
                created_at=now,
                dedup_key=ai_dedup_key,
            )
        )
        session_row = session.get(SessionTable, session_id)
        shop_row = session.get(ShopTable, shop_id)
        if session_row is not None:
            session_row.status = "ai_processing"
            session_row.last_message_preview = reply_text[:100]
            session_row.updated_at = now
        if shop_row is not None:
            shop_row.last_active_at = now
            shop_row.updated_at = now


def _get_global_knowledge_paths() -> list[str]:
    with get_sync_session() as session:
        rows = session.scalars(
            select(KnowledgeFileTable.path)
            .where(KnowledgeFileTable.node_type == "file")
            .order_by(KnowledgeFileTable.sort_order.asc(), KnowledgeFileTable.path.asc())
        ).all()
        return [str(row) for row in rows]


async def process_buyer_message(
    shop_id: str,
    raw_msg: RawMessage,
    llm_client: LlmClient,
    ai_enabled: bool = True,
) -> ProcessResult:
    session_row = _get_or_create_session(shop_id, raw_msg)
    session_id = session_row.id
    message_id = _save_message(session_id, raw_msg)
    if message_id is None:
        return ProcessResult(action="skip", session_id=session_id)

    if not ai_enabled:
        return ProcessResult(action="stored", session_id=session_id, message_id=message_id)

    shop_config = _get_shop_config(shop_id)
    recent_messages = _get_recent_messages(session_id, limit=20)
    escalation_result = check_escalation(
        message_content=raw_msg.content,
        rules=shop_config.get("escalation_rules", []),
        recent_messages=recent_messages[:-1],
    )
    if escalation_result.should_escalate:
        now = raw_msg.timestamp or _iso_now()
        _mark_escalated(shop_id, session_id, escalation_result, shop_config, now)
        return ProcessResult(
            action="escalate",
            session_id=session_id,
            escalation=escalation_result,
            message_id=message_id,
        )

    configured_paths = list(shop_config.get("knowledge_paths", []))
    knowledge_paths = configured_paths
    if bool(shop_config.get("use_global_knowledge", True)):
        knowledge_paths = configured_paths + _get_global_knowledge_paths()

    knowledge_content = _get_knowledge_content(knowledge_paths)
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

    _append_ai_reply(shop_id, session_id, reply_text)

    return ProcessResult(
        action="reply",
        session_id=session_id,
        reply_text=reply_text,
        message_id=message_id,
    )
