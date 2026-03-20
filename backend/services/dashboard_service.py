"""总览聚合查询。"""

from __future__ import annotations

from backend.db.database import get_db
from backend.db.models import DashboardSummary


def get_summary() -> DashboardSummary:
    """聚合仪表盘摘要数据。"""
    with get_db() as conn:
        today_served = conn.execute("SELECT COUNT(DISTINCT session_id) FROM messages").fetchone()[0] or 0
        escalation_count = conn.execute("SELECT COUNT(*) FROM escalation_logs").fetchone()[0] or 0
        ai_replies = conn.execute("SELECT COUNT(*) FROM messages WHERE sender='ai'").fetchone()[0] or 0
        total_replies = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE sender IN ('ai','human')"
        ).fetchone()[0] or 0
        unreplied_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM sessions s
            WHERE EXISTS (
                SELECT 1
                FROM messages buyer_messages
                WHERE buyer_messages.session_id = s.id
                  AND buyer_messages.sender = 'buyer'
            )
              AND COALESCE((
                SELECT last_message.sender
                FROM messages last_message
                WHERE last_message.session_id = s.id
                ORDER BY last_message.created_at DESC, last_message.id DESC
                LIMIT 1
              ), '') NOT IN ('ai', 'human')
            """
        ).fetchone()[0] or 0

    ai_reply_rate = round(ai_replies / total_replies, 4) if total_replies else 0.0
    return DashboardSummary(
        today_served_count=today_served,
        ai_reply_rate=ai_reply_rate,
        escalation_count=escalation_count,
        avg_first_response_ms=0,
        unreplied_count=unreplied_count,
        yesterday_served_count=0,
    )
