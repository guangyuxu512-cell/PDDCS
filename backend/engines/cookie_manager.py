"""Cookie persistence helpers for Playwright browser contexts."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page
from sqlalchemy import select

from backend.core.crypto import decrypt, encrypt, fingerprint
from backend.db.database import get_async_session
from backend.db.orm import ShopCookieTable, ShopTable


logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
PDD_CHAT_URL = "https://mms.pinduoduo.com/chat-merchant/#/"
PDD_HOST = "mms.pinduoduo.com"
PDD_CHAT_PATH = "chat-merchant"
LOGIN_PATH_KEYWORDS = ("login", "passport")
SESSION_ITEM_SELECTOR = "li.chat-item"


async def _wait(awaitable: Any, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


class CookieManager:
    """Saves and restores browser cookies per shop."""

    def __init__(self, data_dir: str = "data/cookies") -> None:
        self._legacy_data_dir = Path(data_dir)

    def _cookie_path(self, shop_id: str) -> Path:
        return self._legacy_data_dir / f"{shop_id}.json"

    async def _persist_cookie_payload(self, shop_id: str, payload: str) -> None:
        now = datetime.now().isoformat()
        encrypted_payload = encrypt(payload)
        payload_fingerprint = fingerprint(payload)

        async with get_async_session() as session:
            shop = await session.get(ShopTable, shop_id)
            if shop is None:
                logger.warning("Skip saving cookies for missing shop %s", shop_id)
                return

            row = await session.get(ShopCookieTable, shop_id)
            if row is None:
                row = ShopCookieTable(shop_id=shop_id)
                session.add(row)

            row.cookie_encrypted = encrypted_payload
            row.cookie_fingerprint = payload_fingerprint
            row.updated_at = now
            shop.cookie_last_refresh = now

    async def save(self, shop_id: str, context: BrowserContext) -> None:
        cookies = await _wait(context.cookies())
        payload = json.dumps(cookies, ensure_ascii=False, separators=(",", ":"))
        await _wait(self._persist_cookie_payload(shop_id, payload), timeout_seconds=5.0)

    async def _load_legacy_file(self, shop_id: str) -> list[dict[str, Any]] | None:
        cookie_path = self._cookie_path(shop_id)
        if not cookie_path.exists():
            return None

        try:
            payload = await _wait(asyncio.to_thread(cookie_path.read_text, encoding="utf-8"), timeout_seconds=5.0)
            cookies = json.loads(payload)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read legacy cookie file for shop %s: %s", shop_id, exc)
            return None

        if not isinstance(cookies, list):
            logger.warning("Legacy cookie payload for shop %s is not a list", shop_id)
            return None

        await self._persist_cookie_payload(shop_id, json.dumps(cookies, ensure_ascii=False, separators=(",", ":")))
        return cookies

    async def load(self, shop_id: str, context: BrowserContext) -> bool:
        async with get_async_session() as session:
            row = await session.get(ShopCookieTable, shop_id)

        cookies: Any = None
        if row is not None and row.cookie_encrypted:
            try:
                cookies = json.loads(decrypt(row.cookie_encrypted))
            except (ValueError, json.JSONDecodeError) as exc:
                logger.warning("Failed to decrypt cookie payload for shop %s: %s", shop_id, exc)
                cookies = None

        if cookies is None:
            cookies = await self._load_legacy_file(shop_id)
            if cookies is None:
                return False

        if not isinstance(cookies, list):
            logger.warning("Cookie payload for shop %s is not a list", shop_id)
            return False

        await _wait(context.add_cookies(cookies))
        return True

    async def is_valid(self, page: Page) -> bool:
        try:
            await _wait(
                page.goto(PDD_CHAT_URL, wait_until="domcontentloaded", timeout=30000),
                timeout_seconds=35.0,
            )
            return "login" not in page.url.lower()
        except Exception as exc:
            logger.warning("Failed to validate cookie state: %s", exc)
            return False

    async def is_valid_without_navigate(self, page: Page) -> bool:
        """Checks whether the current page still has a valid login session without navigating."""
        try:
            current_url = page.url.lower()
            if any(keyword in current_url for keyword in LOGIN_PATH_KEYWORDS):
                logger.warning("Cookie expired: redirected to login page")
                return False

            if PDD_CHAT_PATH not in current_url and PDD_HOST not in current_url:
                logger.warning("Cookie expired: not on PDD page, url=%s", page.url)
                return False

            try:
                element = await _wait(
                    page.query_selector(SESSION_ITEM_SELECTOR),
                    timeout_seconds=3.0,
                )
            except Exception:
                return False

            return element is not None
        except Exception as exc:
            logger.warning("Cookie validation failed: %s", exc)
            return False

    async def periodic_save(self, shop_id: str, context: BrowserContext) -> None:
        """Persists cookies without surfacing periodic-save failures to callers."""
        try:
            await self.save(shop_id, context)
            logger.debug("Periodic cookie save for shop %s", shop_id)
        except Exception:
            logger.exception("Failed periodic cookie save for shop %s", shop_id)
