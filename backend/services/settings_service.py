"""系统设置 CRUD 服务。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from backend.db.database import get_db
from backend.db.models import SystemSettings


_JSON_FIELDS = {"defaultKeywords"}
_NUMBER_FIELDS: dict[str, type[int] | type[float]] = {
    "temperature": float,
    "maxTokens": int,
    "historyRetentionDays": int,
    "maxShops": int,
}


def get_settings() -> SystemSettings:
    """读取系统设置。"""
    with get_db() as conn:
        rows = conn.execute("SELECT key, value FROM system_settings").fetchall()

    raw: dict[str, Any] = {}
    for row in rows:
        key = row["key"]
        value = row["value"]
        if key in _JSON_FIELDS:
            raw[key] = json.loads(value) if value else []
        elif key in _NUMBER_FIELDS:
            raw[key] = _NUMBER_FIELDS[key](value) if value else _NUMBER_FIELDS[key](0)
        else:
            raw[key] = value

    return SystemSettings.model_validate(raw)


def save_settings(body: dict[str, Any]) -> SystemSettings:
    """保存系统设置。"""
    now = datetime.now().isoformat()
    with get_db() as conn:
        for key, value in body.items():
            if key in _JSON_FIELDS:
                db_value = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
            else:
                db_value = "" if value is None else str(value)
            conn.execute(
                """
                INSERT INTO system_settings (key, value, updated_at) VALUES (?,?,?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, db_value, now),
            )
    return get_settings()


def test_llm_connection(api_base_url: str, api_key: str, model: str) -> dict[str, Any]:
    """占位实现：只校验参数完整性。"""
    if not api_base_url.strip() or not api_key.strip() or not model.strip():
        return {"ok": False, "message": "参数不完整"}
    return {"ok": True, "message": f"模型 {model} 连接正常（占位）"}
