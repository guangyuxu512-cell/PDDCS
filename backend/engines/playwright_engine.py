"""Playwright browser engine backed by per-shop persistent contexts."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable
from pathlib import Path
from typing import TypeVar

from playwright.async_api import BrowserContext, Page, Playwright, async_playwright

from backend.engines.cookie_manager import CookieManager
from backend.engines.profile_factory import ProfileFactory


logger = logging.getLogger(__name__)

DEFAULT_PROFILE_BASE_DIR = Path("data/profiles")
DEFAULT_USER_DATA_DIR = DEFAULT_PROFILE_BASE_DIR
DEFAULT_TIMEOUT_SECONDS = 30.0
LAUNCH_TIMEOUT_SECONDS = 60.0
T = TypeVar("T")


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _resolve_chrome_path() -> str:
    return os.getenv("CHROME_PATH", "").strip() or os.getenv("CHROME_EXECUTABLE_PATH", "").strip()


async def _wait(awaitable: Awaitable[T], timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


class PlaywrightEngine:
    """Manages Playwright lifecycle and per-shop persistent contexts."""

    def __init__(self) -> None:
        self._playwright: Playwright | None = None
        self._browser: None = None
        self._contexts: dict[str, BrowserContext] = {}
        self._profile_factory = ProfileFactory(base_dir=str(DEFAULT_PROFILE_BASE_DIR))
        self._cookie_manager = CookieManager()

    async def start(self) -> None:
        """Starts Playwright without launching any browser window."""
        if self._playwright is not None:
            logger.warning("Playwright engine already started")
            return

        self._playwright = await _wait(async_playwright().start(), timeout_seconds=LAUNCH_TIMEOUT_SECONDS)
        logger.info("Playwright engine started")

    async def stop(self) -> None:
        """Closes all shop contexts and stops Playwright."""
        for shop_id in list(self._contexts.keys()):
            await self.close_shop(shop_id)

        if self._playwright is not None:
            await _wait(self._playwright.stop(), timeout_seconds=LAUNCH_TIMEOUT_SECONDS)
            self._playwright = None

        logger.info("Playwright engine stopped")

    def _on_context_closed(self, shop_id: str) -> None:
        self._contexts.pop(shop_id, None)
        logger.info("Persistent context closed for shop %s", shop_id)

    async def _get_or_create_page(self, context: BrowserContext) -> Page:
        for page in context.pages:
            if not page.is_closed():
                return page
        return await _wait(context.new_page())

    async def open_shop(self, shop_id: str, proxy: str = "") -> Page:
        """
        Opens or reuses a persistent context for the given shop.

        Each shop gets an isolated Chrome window and user data directory.
        """
        existing_context = self._contexts.get(shop_id)
        if existing_context is not None:
            return await self._get_or_create_page(existing_context)

        if self._playwright is None:
            raise RuntimeError("Engine not started. Call start() first.")

        user_data_dir = self._profile_factory.get_or_create(shop_id)
        launch_args: dict[str, object] = {
            "channel": "chrome",
            "headless": _env_flag("CHROME_HEADLESS", False),
            "no_viewport": True,
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--disable-infobars",
                "--start-maximized",
            ],
        }

        chrome_path = _resolve_chrome_path()
        if chrome_path:
            launch_args["executable_path"] = chrome_path
            launch_args.pop("channel", None)

        if proxy:
            launch_args["proxy"] = {"server": proxy}

        context = await _wait(
            self._playwright.chromium.launch_persistent_context(user_data_dir, **launch_args),
            timeout_seconds=LAUNCH_TIMEOUT_SECONDS,
        )
        context.on("close", lambda *_: self._on_context_closed(shop_id))
        self._contexts[shop_id] = context

        try:
            await self._cookie_manager.load(shop_id, context)
        except Exception:
            logger.exception("Failed to load cookies for shop %s", shop_id)

        page = await self._get_or_create_page(context)
        logger.info("Opened persistent context for shop %s", shop_id)
        return page

    async def close_shop(self, shop_id: str) -> None:
        """Closes the persistent context for one shop."""
        context = self._contexts.pop(shop_id, None)
        if context is None:
            logger.info("No persistent context to close for shop %s", shop_id)
            return

        try:
            await self._cookie_manager.save(shop_id, context)
        except Exception:
            logger.exception("Failed to save cookies for shop %s", shop_id)
        finally:
            await _wait(context.close(), timeout_seconds=LAUNCH_TIMEOUT_SECONDS)

        logger.info("Closed persistent context for shop %s", shop_id)

    async def get_or_create_context(self, shop_id: str) -> BrowserContext:
        """Backwards-compatible wrapper returning a shop context."""
        existing_context = self._contexts.get(shop_id)
        if existing_context is not None:
            return existing_context
        await self.open_shop(shop_id)
        return self._contexts[shop_id]

    async def get_or_create_page(self, shop_id: str) -> Page:
        """Backwards-compatible wrapper returning a shop page."""
        return await self.open_shop(shop_id)

    async def close_context(self, shop_id: str) -> None:
        """Backwards-compatible wrapper closing a shop context."""
        await self.close_shop(shop_id)

    @property
    def is_running(self) -> bool:
        return self._playwright is not None


engine = PlaywrightEngine()
