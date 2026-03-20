"""店铺 CRUD 服务。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from backend.db.database import get_db
from backend.db.models import Shop, ShopConfig


def _iso_now() -> str:
    return datetime.now().isoformat()


def _default_if_none(data: dict[str, Any], key: str, value: Any) -> None:
    if data.get(key) is None:
        data[key] = value


def list_shops() -> list[Shop]:
    """查询店铺列表。"""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM shops ORDER BY created_at DESC").fetchall()
    return [Shop.model_validate(dict(row)) for row in rows]


def create_shop(name: str, platform: Literal["pdd"], username: str, password: str) -> Shop:
    """创建店铺并插入默认配置。"""
    shop_id = str(uuid.uuid4())
    now = _iso_now()

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO shops (
                id,
                name,
                platform,
                username,
                password,
                is_online,
                ai_enabled,
                cookie_valid,
                today_served_count,
                last_active_at,
                created_at,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                shop_id,
                name,
                platform,
                username,
                password,
                0,
                0,
                0,
                0,
                "",
                now,
                now,
            ),
        )
        conn.execute("INSERT INTO shop_configs (shop_id, updated_at) VALUES (?,?)", (shop_id, now))
        row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()

    if row is None:
        raise RuntimeError("创建店铺失败")

    return Shop.model_validate(dict(row))


def delete_shop(shop_id: str) -> bool:
    """删除店铺。"""
    with get_db() as conn:
        cursor = conn.execute("DELETE FROM shops WHERE id=?", (shop_id,))
    return cursor.rowcount > 0


def toggle_ai(shop_id: str, enabled: bool) -> Shop | None:
    """更新店铺 AI 开关。"""
    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE shops SET ai_enabled=?, updated_at=? WHERE id=?",
            (int(enabled), _iso_now(), shop_id),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
    return Shop.model_validate(dict(row)) if row is not None else None


def toggle_status(shop_id: str) -> Shop | None:
    """翻转店铺在线状态。"""
    with get_db() as conn:
        cursor = conn.execute(
            (
                "UPDATE shops "
                "SET is_online = CASE WHEN is_online=1 THEN 0 ELSE 1 END, updated_at=? "
                "WHERE id=?"
            ),
            (_iso_now(), shop_id),
        )
        if cursor.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
    return Shop.model_validate(dict(row)) if row is not None else None


def scan_desktop_windows() -> list[Shop]:
    """
    桌面窗口扫描占位实现。

    后续实现方式：
    1. 枚举所有顶层窗口 (EnumWindows)
    2. 匹配标题: "千牛工作台"/"AliWorkbench" -> qianniu, "飞鸽"/"抖店" -> douyin
    3. 记录 hwnd，提取店铺名
    4. UPSERT 到 shops 表
    5. 返回新发现的店铺列表
    """
    return []


def get_shop_config(shop_id: str) -> ShopConfig | None:
    """查询店铺配置，不存在配置行时自动创建默认配置。"""
    query = """
        SELECT
            s.id AS shop_id_ref,
            s.name,
            s.username,
            s.password,
            s.platform,
            s.cookie_valid,
            s.cookie_last_refresh,
            s.ai_enabled,
            c.shop_id,
            c.llm_mode,
            c.custom_api_key,
            c.custom_model,
            c.reply_style_note,
            c.knowledge_paths,
            c.use_global_knowledge,
            c.human_agent_name,
            c.escalation_rules,
            c.escalation_fallback_msg
        FROM shops s
        LEFT JOIN shop_configs c ON c.shop_id = s.id
        WHERE s.id = ?
    """

    with get_db() as conn:
        row = conn.execute(query, (shop_id,)).fetchone()
        if row is None:
            return None

        data = dict(row)
        if data.get("shop_id") is None:
            conn.execute("INSERT INTO shop_configs (shop_id) VALUES (?)", (shop_id,))
            data["shop_id"] = shop_id

        data.pop("shop_id_ref", None)
        _default_if_none(data, "llm_mode", "global")
        _default_if_none(data, "custom_api_key", "")
        _default_if_none(data, "custom_model", "")
        _default_if_none(data, "reply_style_note", "")
        _default_if_none(data, "knowledge_paths", "[]")
        _default_if_none(data, "use_global_knowledge", 1)
        _default_if_none(data, "human_agent_name", "")
        _default_if_none(data, "escalation_rules", "[]")
        _default_if_none(data, "escalation_fallback_msg", "")

    return ShopConfig.model_validate(data)


def update_shop_config(shop_id: str, body: dict[str, Any]) -> ShopConfig | None:
    """更新店铺基础信息和配置。"""
    now = _iso_now()

    with get_db() as conn:
        cursor = conn.execute(
            "UPDATE shops SET name=?, username=?, password=?, ai_enabled=?, updated_at=? WHERE id=?",
            (
                body.get("name", ""),
                body.get("username", ""),
                body.get("password", ""),
                int(body.get("aiEnabled", False)),
                now,
                shop_id,
            ),
        )
        if cursor.rowcount == 0:
            return None

        conn.execute(
            """
            INSERT INTO shop_configs (
                shop_id,
                llm_mode,
                custom_api_key,
                custom_model,
                reply_style_note,
                knowledge_paths,
                use_global_knowledge,
                human_agent_name,
                escalation_rules,
                escalation_fallback_msg,
                updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(shop_id) DO UPDATE SET
                llm_mode=excluded.llm_mode,
                custom_api_key=excluded.custom_api_key,
                custom_model=excluded.custom_model,
                reply_style_note=excluded.reply_style_note,
                knowledge_paths=excluded.knowledge_paths,
                use_global_knowledge=excluded.use_global_knowledge,
                human_agent_name=excluded.human_agent_name,
                escalation_rules=excluded.escalation_rules,
                escalation_fallback_msg=excluded.escalation_fallback_msg,
                updated_at=excluded.updated_at
            """,
            (
                shop_id,
                body.get("llmMode", "global"),
                body.get("customApiKey", ""),
                body.get("customModel", ""),
                body.get("replyStyleNote", ""),
                json.dumps(body.get("knowledgePaths", []), ensure_ascii=False),
                int(body.get("useGlobalKnowledge", True)),
                body.get("humanAgentName", ""),
                json.dumps(body.get("escalationRules", []), ensure_ascii=False),
                body.get("escalationFallbackMsg", ""),
                now,
            ),
        )

    return get_shop_config(shop_id)
