"""Cookie persistence helpers for Playwright browser contexts."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Page

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
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)

    def _cookie_path(self, shop_id: str) -> Path:
        return self._data_dir / f"{shop_id}.json"

    async def save(self, shop_id: str, context: BrowserContext) -> None:
        cookies = await _wait(context.cookies())
        payload = json.dumps(cookies, ensure_ascii=False, indent=2)
        await _wait(
            asyncio.to_thread(self._cookie_path(shop_id).write_text, payload, encoding="utf-8"),
            timeout_seconds=5.0,
        )

    async def load(self, shop_id: str, context: BrowserContext) -> bool:
        cookie_path = self._cookie_path(shop_id)
        if not cookie_path.exists():
            return False

        try:
            payload = await _wait(asyncio.to_thread(cookie_path.read_text, encoding="utf-8"), timeout_seconds=5.0)
            cookies = json.loads(payload)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read cookie file for shop %s: %s", shop_id, exc)
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
