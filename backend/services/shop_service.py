"""店铺 CRUD 服务。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.core.crypto import encrypt, hash_password
from backend.db.database import get_sync_session
from backend.db.models import Shop, ShopConfig
from backend.db.orm import ShopConfigTable, ShopCookieTable, ShopTable


def _iso_now() -> str:
    return datetime.now().isoformat()


def _ensure_shop_config_row(shop: ShopTable) -> ShopConfigTable:
    if shop.config is None:
        shop.config = ShopConfigTable(
            shop_id=shop.id,
            updated_at=_iso_now(),
        )
    return shop.config


def _shop_to_model(shop: ShopTable, cookie: ShopCookieTable | None = None) -> Shop:
    resolved_cookie = cookie if cookie is not None else shop.cookie
    return Shop(
        id=shop.id,
        name=shop.name,
        platform=shop.platform,
        is_online=shop.is_online,
        ai_enabled=shop.ai_enabled,
        today_served_count=shop.today_served_count,
        last_active_at=shop.last_active_at,
        cookie_valid=shop.cookie_valid,
        has_password=bool(shop.password_hash or shop.password),
        cookie_fingerprint=resolved_cookie.cookie_fingerprint if resolved_cookie is not None else "",
    )


def _shop_config_to_model(shop: ShopTable, config: ShopConfigTable, cookie: ShopCookieTable | None = None) -> ShopConfig:
    resolved_cookie = cookie if cookie is not None else shop.cookie
    return ShopConfig(
        shop_id=shop.id,
        name=shop.name,
        username=shop.username,
        platform=shop.platform,
        cookie_valid=shop.cookie_valid,
        ai_enabled=shop.ai_enabled,
        has_password=bool(shop.password_hash or shop.password),
        cookie_fingerprint=resolved_cookie.cookie_fingerprint if resolved_cookie is not None else "",
        llm_mode=config.llm_mode,
        custom_api_key=config.custom_api_key,
        custom_model=config.custom_model,
        reply_style_note=config.reply_style_note,
        knowledge_paths=config.knowledge_paths,
        use_global_knowledge=config.use_global_knowledge,
        human_agent_name=config.human_agent_name,
        escalation_rules=config.escalation_rules,
        escalation_fallback_msg=config.escalation_fallback_msg,
        auto_restart=config.auto_restart,
        force_online=config.force_online,
    )


def list_shops() -> list[Shop]:
    with get_sync_session() as session:
        shops = session.scalars(
            select(ShopTable)
            .options(selectinload(ShopTable.cookie))
            .order_by(ShopTable.created_at.desc())
        ).all()
        return [_shop_to_model(shop) for shop in shops]


def create_shop(name: str, platform: Literal["pdd"], username: str, password: str) -> Shop:
    shop_id = str(uuid.uuid4())
    now = _iso_now()
    encrypted_password = encrypt(password)
    password_hash = hash_password(password)

    with get_sync_session() as session:
        shop = ShopTable(
            id=shop_id,
            name=name,
            platform=platform,
            username=username,
            password="",
            password_encrypted=encrypted_password,
            password_hash=password_hash,
            is_online=False,
            ai_enabled=False,
            cookie_valid=False,
            cookie_last_refresh="",
            today_served_count=0,
            last_active_at="",
            created_at=now,
            updated_at=now,
        )
        shop.config = ShopConfigTable(shop_id=shop_id, updated_at=now)
        session.add(shop)
        session.flush()
        session.refresh(shop)
        return _shop_to_model(shop)


def delete_shop(shop_id: str) -> bool:
    with get_sync_session() as session:
        shop = session.get(ShopTable, shop_id)
        if shop is None:
            return False
        session.delete(shop)
        return True


def toggle_ai(shop_id: str, enabled: bool) -> Shop | None:
    with get_sync_session() as session:
        shop = session.get(ShopTable, shop_id)
        if shop is None:
            return None

        shop.ai_enabled = enabled
        shop.updated_at = _iso_now()
        session.flush()
        return _shop_to_model(shop)


def toggle_status(shop_id: str) -> Shop | None:
    with get_sync_session() as session:
        shop = session.get(ShopTable, shop_id)
        if shop is None:
            return None

        shop.is_online = not shop.is_online
        shop.updated_at = _iso_now()
        session.flush()
        return _shop_to_model(shop)


def scan_desktop_windows() -> list[Shop]:
    return []


def get_shop_config(shop_id: str) -> ShopConfig | None:
    with get_sync_session() as session:
        shop = session.scalar(
            select(ShopTable)
            .options(
                selectinload(ShopTable.config),
                selectinload(ShopTable.cookie),
            )
            .where(ShopTable.id == shop_id)
        )
        if shop is None:
            return None

        config = _ensure_shop_config_row(shop)
        session.flush()
        return _shop_config_to_model(shop, config)


def update_shop_config(shop_id: str, body: dict[str, Any]) -> ShopConfig | None:
    now = _iso_now()

    with get_sync_session() as session:
        shop = session.scalar(
            select(ShopTable)
            .options(
                selectinload(ShopTable.config),
                selectinload(ShopTable.cookie),
            )
            .where(ShopTable.id == shop_id)
        )
        if shop is None:
            return None

        config = _ensure_shop_config_row(shop)

        shop.name = str(body.get("name", shop.name))
        shop.username = str(body.get("username", shop.username))
        shop.ai_enabled = bool(body.get("aiEnabled", shop.ai_enabled))
        shop.updated_at = now

        raw_password = str(body.get("password", "") or "").strip()
        if raw_password:
            shop.password = ""
            shop.password_encrypted = encrypt(raw_password)
            shop.password_hash = hash_password(raw_password)

        config.llm_mode = str(body.get("llmMode", config.llm_mode or "global"))
        config.custom_api_key = str(body.get("customApiKey", config.custom_api_key or ""))
        config.custom_model = str(body.get("customModel", config.custom_model or ""))
        config.reply_style_note = str(body.get("replyStyleNote", config.reply_style_note or ""))
        config.knowledge_paths = json.dumps(body.get("knowledgePaths", []), ensure_ascii=False)
        config.use_global_knowledge = bool(body.get("useGlobalKnowledge", config.use_global_knowledge))
        config.human_agent_name = str(body.get("humanAgentName", config.human_agent_name or ""))
        config.escalation_rules = json.dumps(body.get("escalationRules", []), ensure_ascii=False)
        config.escalation_fallback_msg = str(
            body.get("escalationFallbackMsg", config.escalation_fallback_msg or "")
        )
        config.auto_restart = bool(body.get("autoRestart", config.auto_restart))
        config.force_online = bool(body.get("forceOnline", config.force_online))
        config.updated_at = now

        session.flush()
        return _shop_config_to_model(shop, config)
