"""总览聚合查询。"""

from __future__ import annotations

from backend.db.database import get_db
from backend.db.models import DashboardSummary


def get_summary() -> DashboardSummary:
    """聚合仪表盘摘要数据。"""
    today_expr = "date('now','localtime')"
    yesterday_expr = "date('now','localtime','-1 day')"

    with get_db() as conn:
        today_served = conn.execute(
            f"SELECT COUNT(DISTINCT session_id) FROM messages WHERE date(created_at) = {today_expr}"
        ).fetchone()[0] or 0
        yesterday_served = conn.execute(
            f"SELECT COUNT(DISTINCT session_id) FROM messages WHERE date(created_at) = {yesterday_expr}"
        ).fetchone()[0] or 0
        escalation_count = conn.execute(
            f"SELECT COUNT(*) FROM escalation_logs WHERE date(created_at) = {today_expr}"
        ).fetchone()[0] or 0
        ai_replies = conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE sender='ai' AND date(created_at) = {today_expr}"
        ).fetchone()[0] or 0
        total_replies = conn.execute(
            (
                f"SELECT COUNT(*) FROM messages "
                f"WHERE sender IN ('ai','human') AND date(created_at) = {today_expr}"
            )
        ).fetchone()[0] or 0
        unreplied_count = conn.execute(
            f"""
            SELECT COUNT(*) FROM sessions s
            WHERE EXISTS (
                SELECT 1
                FROM messages buyer_messages
                WHERE buyer_messages.session_id = s.id
                  AND buyer_messages.sender = 'buyer'
                  AND date(buyer_messages.created_at) = {today_expr}
            )
              AND NOT EXISTS (
                SELECT 1
                FROM messages reply_messages
                WHERE reply_messages.session_id = s.id
                  AND reply_messages.sender IN ('ai','human')
                  AND date(reply_messages.created_at) = {today_expr}
                  AND reply_messages.created_at > (
                      SELECT MAX(last_buyer.created_at)
                      FROM messages last_buyer
                      WHERE last_buyer.session_id = s.id
                        AND last_buyer.sender = 'buyer'
                        AND date(last_buyer.created_at) = {today_expr}
                  )
            )
            """
        ).fetchone()[0] or 0

    ai_reply_rate = round(ai_replies / total_replies, 4) if total_replies else 0.0
    return DashboardSummary(
        today_served_count=today_served,
        ai_reply_rate=ai_reply_rate,
        escalation_count=escalation_count,
        avg_first_response_ms=0,
        unreplied_count=unreplied_count,
        yesterday_served_count=yesterday_served,
    )
