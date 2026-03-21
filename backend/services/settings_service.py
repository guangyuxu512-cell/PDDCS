"""系统设置 CRUD 服务。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import select

from backend.db.database import get_sync_session
from backend.db.models import SystemSettings
from backend.db.orm import SystemSettingTable


_JSON_FIELDS = {"defaultKeywords"}
_NUMBER_FIELDS: dict[str, type[int] | type[float]] = {
    "temperature": float,
    "maxTokens": int,
    "historyRetentionDays": int,
    "maxShops": int,
}


def get_settings() -> SystemSettings:
    with get_sync_session() as session:
        rows = session.scalars(select(SystemSettingTable).order_by(SystemSettingTable.key)).all()

    raw: dict[str, Any] = {}
    for row in rows:
        key = row.key
        value = row.value
        if key in _JSON_FIELDS:
            raw[key] = json.loads(value) if value else []
        elif key in _NUMBER_FIELDS:
            raw[key] = _NUMBER_FIELDS[key](value) if value else _NUMBER_FIELDS[key](0)
        else:
            raw[key] = value

    if "notifyWebhookUrl" not in raw and "alertWebhookUrl" in raw:
        raw["notifyWebhookUrl"] = raw["alertWebhookUrl"]
    raw.setdefault("notifyWebhookType", "feishu")

    return SystemSettings.model_validate(raw)


def save_settings(body: dict[str, Any]) -> SystemSettings:
    now = datetime.now().isoformat()
    normalized_body = dict(body)
    if "notifyWebhookUrl" in normalized_body and "alertWebhookUrl" not in normalized_body:
        normalized_body["alertWebhookUrl"] = normalized_body["notifyWebhookUrl"]

    with get_sync_session() as session:
        for key, value in normalized_body.items():
            row = session.get(SystemSettingTable, key)
            if row is None:
                row = SystemSettingTable(key=key, value="", updated_at=now)
                session.add(row)

            if key in _JSON_FIELDS:
                row.value = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else str(value)
            else:
                row.value = "" if value is None else str(value)
            row.updated_at = now

    return get_settings()


def test_llm_connection(api_base_url: str, api_key: str, model: str) -> dict[str, Any]:
    if not api_base_url.strip() or not api_key.strip() or not model.strip():
        return {"ok": False, "message": "参数不完整"}
    return {"ok": True, "message": f"模型 {model} 连接正常（占位）"}
