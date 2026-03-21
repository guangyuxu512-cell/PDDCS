"""对话监控服务。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.db.database import get_sync_session
from backend.db.models import ChatSession
from backend.db.orm import MessageTable, SessionTable, orm_object_to_dict


def _build_session(session_row: SessionTable) -> ChatSession:
    payload = orm_object_to_dict(session_row)
    payload["messages"] = [orm_object_to_dict(message) for message in session_row.messages]
    return ChatSession.model_validate(payload)


def list_sessions() -> list[ChatSession]:
    with get_sync_session() as session:
        rows = session.scalars(
            select(SessionTable)
            .options(selectinload(SessionTable.messages))
            .order_by(SessionTable.updated_at.desc())
        ).all()
        return [_build_session(row) for row in rows]


def takeover_session(session_id: str) -> ChatSession | None:
    with get_sync_session() as session:
        row = session.scalar(
            select(SessionTable)
            .options(selectinload(SessionTable.messages))
            .where(SessionTable.id == session_id)
        )
        if row is None:
            return None
        row.status = "escalated"
        row.updated_at = datetime.now().isoformat()
        session.flush()
        session.refresh(row, attribute_names=["messages"])
        return _build_session(row)
