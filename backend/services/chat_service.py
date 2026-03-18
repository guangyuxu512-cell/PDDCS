"""对话监控服务。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.db.database import get_db
from backend.db.models import ChatSession


def _build_session(conn: Any, session_id: str) -> ChatSession | None:
    row = conn.execute("SELECT * FROM sessions WHERE id=?", (session_id,)).fetchone()
    if row is None:
        return None
    data = dict(row)
    message_rows = conn.execute(
        "SELECT * FROM messages WHERE session_id=? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()
    data["messages"] = [dict(message_row) for message_row in message_rows]
    return ChatSession.model_validate(data)


def list_sessions() -> list[ChatSession]:
    """查询所有会话及其消息。"""
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM sessions ORDER BY updated_at DESC").fetchall()
        sessions = [_build_session(conn, row["id"]) for row in rows]
    return [session for session in sessions if session is not None]


def takeover_session(session_id: str) -> ChatSession | None:
    """人工接管会话。"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET status='escalated', updated_at=? WHERE id=?",
            (datetime.now().isoformat(), session_id),
        )
        if cursor.rowcount == 0:
            return None
        return _build_session(conn, session_id)
