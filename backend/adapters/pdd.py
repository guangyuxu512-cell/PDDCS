"""拼多多客服页 RPA 适配器。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable
from datetime import datetime
from typing import TypeVar

from playwright.async_api import ElementHandle, Page, TimeoutError as PlaywrightTimeoutError

from backend.adapters.base import BaseAdapter, RawMessage, SessionInfo
from backend.adapters.selector_config import SelectorConfig
from backend.engines.human_simulator import HumanSimulator


logger = logging.getLogger(__name__)


def _selector(primary: str, *fallbacks: str) -> SelectorConfig:
    return SelectorConfig(primary=primary, fallbacks=list(fallbacks) or None)


SELECTORS: dict[str, SelectorConfig] = {
    "session_list": _selector(".chat-list", ".session-list", "[class='chatList']", "[class='sessionList']"),
    "session_item": _selector(
        ".chat-list-item",
        ".session-item",
        "[class='chatListItem']",
        "[class='sessionItem']",
    ),
    "buyer_name": _selector(
        ".buyer-name",
        ".nick-name",
        "[class='buyerName']",
        "[class='nickName']",
        "[class*='userName']",
    ),
    "last_message": _selector(
        ".last-msg",
        ".msg-preview",
        "[class='lastMsg']",
        "[class='msgPreview']",
    ),
    "unread_badge": _selector(".unread-badge", ".badge", "[class='unread']", "[class='badge']"),
    "message_container": _selector(
        ".chat-content",
        ".message-list",
        "[class='chatContent']",
        "[class='messageList']",
        "[class*='msgList']",
    ),
    "message_item": _selector(".msg-item", ".message-item", "[class='msgItem']", "[class='messageItem']"),
    "message_text": _selector(
        ".msg-text",
        ".text-content",
        "[class='msgText']",
        "[class='textContent']",
        "[class*='msgContent']",
    ),
    "message_sender_buyer": _selector(
        ".buyer-msg",
        ".msg-left",
        "[class='buyerMsg']",
        "[class='msgLeft']",
        "[class*='receive']",
    ),
    "message_sender_self": _selector(
        ".self-msg",
        ".msg-right",
        "[class='selfMsg']",
        "[class='msgRight']",
        "[class*='send']",
    ),
    "input_box": _selector(
        ".chat-input textarea",
        ".msg-input textarea",
        "[class='chatInput'] textarea",
        "[class='editorInner']",
        "textarea[class*='input']",
    ),
    "send_button": _selector(".send-btn", ".btn-send", "[class='sendBtn']", "button[class='send']"),
    "transfer_button": _selector(".transfer-btn", "[class='transfer']", "[class='escalat']"),
    "agent_select": _selector(".agent-list", "[class='agentList']", "[class='staffList']"),
    "agent_item": _selector(".agent-item", "[class='agentItem']", "[class='staffItem']"),
}
PDD_CHAT_URL = "https://mms.pinduoduo.com/chat-merchant/#/"
DEFAULT_TIMEOUT_SECONDS = 10.0
T = TypeVar("T")


async def _wait(awaitable: Awaitable[T], timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _selector_timeout_seconds(timeout_ms: int) -> float:
    return max((timeout_ms / 1000) + 1.0, 1.0)


class PddAdapter(BaseAdapter):
    """拼多多客服页 RPA 适配器。"""

    def __init__(self, page: Page, shop_id: str, human_simulator: HumanSimulator | None = None) -> None:
        self._page = page
        self._shop_id = shop_id
        self._human_simulator = human_simulator or HumanSimulator(page)
        self._current_session_id: str | None = None

    async def _query_selector(
        self,
        scope: Page | ElementHandle,
        selector_key: str,
    ) -> ElementHandle | None:
        for selector in SELECTORS[selector_key].all():
            try:
                element = await _wait(scope.query_selector(selector))
            except Exception:
                continue
            if element is not None:
                return element
        return None

    async def _query_selector_all(
        self,
        scope: Page | ElementHandle,
        selector_key: str,
    ) -> list[ElementHandle]:
        for selector in SELECTORS[selector_key].all():
            try:
                elements = await _wait(scope.query_selector_all(selector))
            except Exception:
                continue
            if elements:
                return elements
        return []

    async def _wait_for_selector(self, selector_key: str, timeout_ms: int) -> ElementHandle | None:
        selectors = SELECTORS[selector_key].all()
        per_selector_timeout_ms = max(timeout_ms // max(len(selectors), 1), 1)
        last_error: Exception | None = None
        for selector in selectors:
            try:
                return await _wait(
                    self._page.wait_for_selector(selector, timeout=per_selector_timeout_ms),
                    timeout_seconds=_selector_timeout_seconds(per_selector_timeout_ms),
                )
            except (PlaywrightTimeoutError, TimeoutError) as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        return None

    async def navigate_to_chat(self) -> None:
        """导航到拼多多客服聊天页。"""
        if "mms.pinduoduo.com/chat-merchant" in self._page.url:
            logger.info("Already on PDD chat page")
            return

        logger.info("Navigating to %s", PDD_CHAT_URL)
        await _wait(
            self._page.goto(PDD_CHAT_URL, wait_until="networkidle", timeout=30000),
            timeout_seconds=35.0,
        )
        try:
            await self._wait_for_selector("session_list", timeout_ms=10000)
            logger.info("PDD chat page loaded, session list visible")
        except (PlaywrightTimeoutError, TimeoutError):
            logger.warning("Session list not found, manual login may be required")

    async def get_session_list(self) -> list[SessionInfo]:
        """读取左侧会话列表。"""
        sessions: list[SessionInfo] = []
        items = await self._query_selector_all(self._page, "session_item")
        for index, item in enumerate(items):
            try:
                name_el = await self._query_selector(item, "buyer_name")
                buyer_name = (await _wait(name_el.inner_text())).strip() if name_el is not None else f"买家{index + 1}"

                msg_el = await self._query_selector(item, "last_message")
                last_message = (await _wait(msg_el.inner_text())).strip() if msg_el is not None else ""

                unread_el = await self._query_selector(item, "unread_badge")
                session_id = buyer_name or f"session-{index + 1}"
                sessions.append(
                    SessionInfo(
                        session_id=session_id,
                        buyer_id=session_id,
                        buyer_name=buyer_name or session_id,
                        last_message=last_message,
                        unread=unread_el is not None,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to parse session item %s: %s", index, exc)
        logger.info("Found %s sessions", len(sessions))
        return sessions

    async def switch_to_session(self, session_id: str) -> None:
        """点击左侧会话列表切换到指定会话。"""
        items = await self._query_selector_all(self._page, "session_item")
        for item in items:
            name_el = await self._query_selector(item, "buyer_name")
            if name_el is None:
                continue
            name = (await _wait(name_el.inner_text())).strip()
            if name == session_id:
                await self._human_simulator.bezier_click(item)
                self._current_session_id = session_id
                await _wait(self._page.wait_for_timeout(500), timeout_seconds=2.0)
                logger.info("Switched to session: %s", session_id)
                return
        logger.warning("Session not found: %s", session_id)

    async def fetch_messages(self, session_id: str) -> list[RawMessage]:
        """抓取当前会话的所有可见消息。"""
        if self._current_session_id != session_id:
            await self.switch_to_session(session_id)

        messages: list[RawMessage] = []
        now = datetime.now().isoformat()
        items = await self._query_selector_all(self._page, "message_item")
        for index, item in enumerate(items):
            try:
                text_el = await self._query_selector(item, "message_text")
                if text_el is None:
                    continue

                content = (await _wait(text_el.inner_text())).strip()
                if not content:
                    continue

                is_buyer = await self._query_selector(item, "message_sender_buyer")
                sender = "buyer" if is_buyer is not None else "human"
                content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
                dedup_key = f"{self._shop_id}:{session_id}:{index}:{content_hash}"
                messages.append(
                    RawMessage(
                        session_id=session_id,
                        buyer_id=session_id,
                        buyer_name=session_id,
                        content=content,
                        sender=sender,
                        timestamp=now,
                        dedup_key=dedup_key,
                    )
                )
            except Exception as exc:
                logger.warning("Failed to parse message %s: %s", index, exc)
        logger.debug("Fetched %s messages from session %s", len(messages), session_id)
        return messages

    async def send_message(self, session_id: str, text: str) -> bool:
        """在当前会话输入并发送消息。"""
        if self._current_session_id != session_id:
            await self.switch_to_session(session_id)

        try:
            input_box = await self._wait_for_selector("input_box", timeout_ms=5000)
            if input_box is None:
                logger.error("Input box not found")
                return False

            await self._human_simulator.simulate_typing(input_box, text)
            await _wait(self._page.wait_for_timeout(300), timeout_seconds=1.0)

            send_button = await self._query_selector(self._page, "send_button")
            if send_button is not None:
                await self._human_simulator.bezier_click(send_button)
            else:
                await _wait(input_box.press("Enter"), timeout_seconds=2.0)

            await _wait(self._page.wait_for_timeout(500), timeout_seconds=1.5)
            logger.info("Sent message to %s: %s", session_id, text[:30])
            return True
        except Exception as exc:
            logger.error("Failed to send message: %s", exc)
            return False

    async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
        """点击转人工并选择目标客服。"""
        if self._current_session_id != session_id:
            await self.switch_to_session(session_id)

        try:
            transfer_button = await self._wait_for_selector("transfer_button", timeout_ms=5000)
            if transfer_button is None:
                logger.error("Transfer button not found")
                return False

            await _wait(transfer_button.click(), timeout_seconds=2.0)
            await _wait(self._page.wait_for_timeout(500), timeout_seconds=1.5)
            agent_items = await self._query_selector_all(self._page, "agent_item")
            for agent_item in agent_items:
                agent_name = (await _wait(agent_item.inner_text())).strip()
                if target_agent in agent_name:
                    await _wait(agent_item.click(), timeout_seconds=2.0)
                    await _wait(self._page.wait_for_timeout(500), timeout_seconds=1.5)
                    logger.info("Escalated session %s to %s", session_id, target_agent)
                    return True

            logger.warning("Target agent '%s' not found in agent list", target_agent)
            return False
        except Exception as exc:
            logger.error("Escalation failed: %s", exc)
            return False

    async def is_logged_in(self) -> bool:
        """检查是否已登录。"""
        try:
            element = await self._query_selector(self._page, "session_list")
            return element is not None
        except Exception:
            return False

    async def wait_for_login(self, timeout_ms: int = 120000) -> bool:
        """等待用户手动登录。"""
        logger.info("Waiting for manual login...")
        try:
            await self._wait_for_selector("session_list", timeout_ms=timeout_ms)
            logger.info("Login detected")
            return True
        except (PlaywrightTimeoutError, TimeoutError):
            logger.error("Login timeout")
            return False
