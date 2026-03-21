"""总览聚合查询。"""

from __future__ import annotations

from sqlalchemy import exists, func, select

from backend.db.database import get_sync_session
from backend.db.models import DashboardSummary
from backend.db.orm import EscalationLogTable, MessageTable, SessionTable


def get_summary() -> DashboardSummary:
    last_sender_subquery = (
        select(MessageTable.sender)
        .where(MessageTable.session_id == SessionTable.id)
        .order_by(MessageTable.created_at.desc(), MessageTable.id.desc())
        .limit(1)
        .scalar_subquery()
    )
    buyer_exists = exists(
        select(1).where(
            MessageTable.session_id == SessionTable.id,
            MessageTable.sender == "buyer",
        )
    )

    with get_sync_session() as session:
        today_served = session.scalar(select(func.count(func.distinct(MessageTable.session_id)))) or 0
        escalation_count = session.scalar(select(func.count()).select_from(EscalationLogTable)) or 0
        ai_replies = session.scalar(
            select(func.count()).select_from(MessageTable).where(MessageTable.sender == "ai")
        ) or 0
        total_replies = session.scalar(
            select(func.count())
            .select_from(MessageTable)
            .where(MessageTable.sender.in_(("ai", "human")))
        ) or 0
        unreplied_count = session.scalar(
            select(func.count())
            .select_from(SessionTable)
            .where(
                buyer_exists,
                func.coalesce(last_sender_subquery, "").not_in(("ai", "human")),
            )
        ) or 0

    ai_reply_rate = round(ai_replies / total_replies, 4) if total_replies else 0.0
    return DashboardSummary(
        today_served_count=int(today_served),
        ai_reply_rate=ai_reply_rate,
        escalation_count=int(escalation_count),
        avg_first_response_ms=0,
        unreplied_count=int(unreplied_count),
        yesterday_served_count=0,
    )
