"""SQLite 种子数据脚本，用于前后端联调。"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta

from backend.db.database import get_db, init_database


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


_NAMESPACE = uuid.UUID("d9930d78-5bd2-4548-a90b-6fe58f3a39f0")


def _stable_uuid(name: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, name))


def seed_database() -> None:
    """插入前后端联调用的种子数据。"""
    init_database()

    now = datetime.now().replace(microsecond=0)
    shop_a_id = _stable_uuid("shop:pdd")
    shop_b_id = _stable_uuid("shop:douyin")

    session_1_id = _stable_uuid("session:buyer-zhangsan")
    session_2_id = _stable_uuid("session:buyer-lisi")
    session_3_id = _stable_uuid("session:buyer-wangwu")

    folder_id = _stable_uuid("knowledge:folder:after-sale")
    refund_file_id = _stable_uuid("knowledge:file:refund")
    logistics_file_id = _stable_uuid("knowledge:file:logistics")

    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO shops (
                id,
                name,
                platform,
                username,
                password,
                is_online,
                ai_enabled,
                cookie_valid,
                today_served_count,
                last_active_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                shop_a_id,
                "测试拼多多店铺",
                "pdd",
                "pdd_test",
                "123456",
                1,
                1,
                1,
                35,
                now.isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO shops (
                id,
                name,
                platform,
                username,
                password,
                is_online,
                ai_enabled,
                cookie_valid,
                today_served_count,
                last_active_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                shop_b_id,
                "测试抖店",
                "douyin",
                "dy_test",
                "123456",
                0,
                0,
                0,
                0,
                "",
            ),
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO shop_configs (
                shop_id,
                knowledge_paths,
                use_global_knowledge,
                human_agent_name,
                escalation_rules
            ) VALUES (?,?,?,?,?)
            """,
            (
                shop_a_id,
                json.dumps(["退款话术.md"], ensure_ascii=False),
                1,
                "客服小王",
                json.dumps(
                    [{"id": "r1", "type": "keyword", "value": "退款,投诉"}],
                    ensure_ascii=False,
                ),
            ),
        )
        conn.execute("INSERT OR IGNORE INTO shop_configs (shop_id) VALUES (?)", (shop_b_id,))

        conn.execute(
            """
            INSERT OR IGNORE INTO sessions (
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
                session_1_id,
                shop_a_id,
                "测试拼多多店铺",
                "pdd",
                "buyer_zhangsan",
                "买家张三",
                "ai_processing",
                "亲，您的订单已经发出，预计明天到达哦~",
                now.isoformat(),
                (now - timedelta(minutes=10)).isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions (
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
                session_2_id,
                shop_a_id,
                "测试拼多多店铺",
                "pdd",
                "buyer_lisi",
                "买家李四",
                "escalated",
                "我要投诉",
                (now - timedelta(minutes=5)).isoformat(),
                (now - timedelta(minutes=20)).isoformat(),
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions (
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
                session_3_id,
                shop_a_id,
                "测试拼多多店铺",
                "pdd",
                "buyer_wangwu",
                "买家王五",
                "closed",
                "谢谢，已解决",
                (now - timedelta(hours=1)).isoformat(),
                (now - timedelta(hours=2)).isoformat(),
            ),
        )

        messages = [
            ("message:1", session_1_id, "buyer", "你好，我买的东西还没发货", now - timedelta(minutes=4)),
            ("message:2", session_1_id, "ai", "亲，帮您查一下订单状态，请稍等~", now - timedelta(minutes=3)),
            ("message:3", session_1_id, "buyer", "好的谢谢", now - timedelta(minutes=2)),
            (
                "message:4",
                session_1_id,
                "ai",
                "亲，您的订单已经发出，预计明天到达哦~",
                now - timedelta(minutes=1),
            ),
        ]
        for message_name, session_id, sender, content, created_at in messages:
            conn.execute(
                """
                INSERT OR IGNORE INTO messages (
                    id,
                    session_id,
                    sender,
                    content,
                    created_at,
                    dedup_key
                ) VALUES (?,?,?,?,?,?)
                """,
                (
                    _stable_uuid(message_name),
                    session_id,
                    sender,
                    content,
                    created_at.isoformat(),
                    f"{session_id}:{message_name}",
                ),
            )

        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_files (
                id,
                name,
                path,
                node_type,
                parent_path,
                content,
                sort_order
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (folder_id, "售后话术", "售后话术", "folder", None, "", 0),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_files (
                id,
                name,
                path,
                node_type,
                parent_path,
                content,
                sort_order
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                refund_file_id,
                "退款话术.md",
                "售后话术/退款话术.md",
                "file",
                "售后话术",
                "# 退款话术\n\n1. 亲，非常抱歉给您带来不好的体验...",
                1,
            ),
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO knowledge_files (
                id,
                name,
                path,
                node_type,
                parent_path,
                content,
                sort_order
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                logistics_file_id,
                "物流话术.md",
                "售后话术/物流话术.md",
                "file",
                "售后话术",
                "# 物流话术\n\n1. 亲，帮您查一下物流信息...",
                2,
            ),
        )


def main() -> None:
    seed_database()
    print("✅ 种子数据插入完成")


if __name__ == "__main__":
    main()
