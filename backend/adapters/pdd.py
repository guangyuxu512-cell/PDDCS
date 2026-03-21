"""拼多多客服页 RPA 适配器。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from collections.abc import Awaitable
from datetime import datetime
from typing import TypeVar

from playwright.async_api import ElementHandle, Frame, Page, TimeoutError as PlaywrightTimeoutError

from backend.adapters.base import BaseAdapter, RawMessage, SessionInfo
from backend.adapters.selector_config import SelectorConfig
from backend.engines.human_simulator import HumanSimulator
from backend.services.notifier import send_notification


logger = logging.getLogger(__name__)


def _selector(primary: str, *fallbacks: str) -> SelectorConfig:
    return SelectorConfig(primary=primary, fallbacks=list(fallbacks) or None)


SELECTORS: dict[str, SelectorConfig] = {
    "login_tab": _selector(".login-tab div:has-text('账号登录')"),
    "login_username": _selector("#usernameId"),
    "login_password": _selector("#passwordId"),
    "login_submit": _selector("button:has-text('登录')"),
    "session_list": _selector(
        "ul:has(> li.chat-item)",
        "[class*='chat-list']",
    ),
    "session_item": _selector("li.chat-item"),
    "buyer_name": _selector(
        ".chat-detail .nickname-span",
        ".chat-nickname .nickname-span",
    ),
    "last_message": _selector(
        ".chat-detail .chat-message-content",
        ".bottom-message .chat-message-content",
    ),
    "unread_badge": _selector(
        ".chat-unreply-time",
        "[class*='unread']",
    ),
    "message_container": _selector(".merchantMessage"),
    "message_item": _selector(
        ".merchantMessage .buyer-item",
        ".merchantMessage .seller-item",
        ".merchantMessage .robot-item",
    ),
    "message_text": _selector(".msg-content-box"),
    "message_index": _selector(".msg-content"),
    "message_sender_buyer": _selector(".buyer-item"),
    "message_sender_self": _selector(
        ".seller-item",
        ".robot-item",
    ),
    "input_box": _selector(
        "textarea#replyTextarea",
        "textarea.custom-scroll",
    ),
    "send_button": _selector(
        "div.send-btn",
        "[class='send-btn']",
    ),
    "transfer_button": _selector(
        ".checkbox-transfer-btn",
        ".transfer-chat-item-btn",
    ),
    "agent_select": _selector(".agent-list", "[class*='agentList']", "[class*='staffList']"),
    "agent_item": _selector(".agent-item", "[class*='agentItem']", "[class*='staffItem']"),
    "login_tab_account": _selector(
        ".login-tab div:has-text('账号登录')",
        "text=账号登录",
        ".login-tab-item",
    ),
    "login_button": _selector(
        "button:has-text('登录')",
        "button[type='submit']",
    ),
    "login_captcha_slider": _selector(
        ".captcha-container",
        ".captcha-slider",
        ".sc-jrQzAO",
        "#captcha_container",
    ),
    "login_sms_input": _selector(
        "input[placeholder='请输入短信验证码']",
        "input[placeholder*='验证码']",
        "input[placeholder*='短信']",
    ),
    "session_timeout_hint": _selector(
        "div:has-text('网络异常')",
        "div:has-text('请刷新页面')",
        "div:has-text('页面已过期')",
        "div:has-text('连接已断开')",
        ".network-error",
        ".page-expired",
    ),
    "session_timeout_refresh_btn": _selector(
        "button:has-text('刷新')",
        "button:has-text('重新加载')",
        "a:has-text('刷新页面')",
    ),
    "online_status_indicator": _selector(
        ".online-status",
        "[class*='onlineStatus']",
        "[class*='service-status']",
        ".status-indicator",
    ),
    "online_status_text": _selector(
        ".online-status-text",
        "[class*='statusText']",
        "span:has-text('在线')",
        "span:has-text('离线')",
        "span:has-text('忙碌')",
    ),
    "online_switch_button": _selector(
        ".online-switch",
        "[class*='onlineSwitch']",
        "button:has-text('上线')",
        "button:has-text('恢复在线')",
        ".status-toggle",
    ),
    "popup_dismiss_today": _selector(
        "a:has-text('今天不再提示')",
        "span:has-text('今天不再提示')",
        "div:has-text('今天不再提示') >> visible=true",
    ),
    "popup_dismiss_ok": _selector(
        "button:has-text('我知道了')",
        "a:has-text('我知道了')",
        "div.btn:has-text('我知道了')",
    ),
    "popup_close_icon": _selector(
        ".modal-close",
        ".popup-close",
        "[class*='close-btn']",
        "[class*='closeBtn']",
        ".ant-modal-close",
    ),
}
PDD_CHAT_URL = "https://mms.pinduoduo.com/chat-merchant/#/"
PDD_LOGIN_URL = "https://mms.pinduoduo.com/login/"
DEFAULT_TIMEOUT_SECONDS = 10.0
T = TypeVar("T")
SelectorScope = Page | Frame | ElementHandle
ChatScope = Page | Frame


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
        self._chat_frame: ChatScope | None = None

    async def _query_selector(
        self,
        scope: SelectorScope,
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
        scope: SelectorScope,
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

    async def _wait_for_selector_keys(
        self,
        selector_keys: tuple[str, ...],
        timeout_ms: int,
    ) -> ElementHandle | None:
        per_key_timeout_ms = max(timeout_ms // max(len(selector_keys), 1), 1)
        last_error: Exception | None = None
        for selector_key in selector_keys:
            try:
                return await self._wait_for_selector(selector_key, timeout_ms=per_key_timeout_ms)
            except (PlaywrightTimeoutError, TimeoutError) as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        return None

    async def _wait_for_logged_in_element(self, timeout_ms: int) -> bool:
        try:
            await self._wait_for_selector_keys(("session_item", "session_list"), timeout_ms=timeout_ms)
            return True
        except (PlaywrightTimeoutError, TimeoutError):
            return False

    async def _find_chat_frame(self) -> ChatScope:
        """查找聊天消息所在的执行上下文（主页面或子 frame）。"""
        try:
            container = await _wait(
                self._page.query_selector(SELECTORS["message_container"].primary),
                timeout_seconds=3.0,
            )
            if container is not None:
                logger.info("Chat messages found in main page")
                return self._page
        except Exception:
            pass

        for frame in self._page.frames:
            try:
                container = await _wait(
                    frame.query_selector(SELECTORS["message_container"].primary),
                    timeout_seconds=2.0,
                )
            except Exception:
                continue
            if container is not None:
                logger.info("Chat messages found in frame: %s", frame.url)
                return frame

        logger.warning("merchantMessage not found in any frame, using main page")
        return self._page

    async def _is_on_login_page(self) -> bool:
        """检查当前是否处于登录页。"""
        url = self._page.url.lower()
        return "login" in url or "passport" in url

    async def navigate_to_chat(self, username: str = "", password: str = "") -> None:
        """导航到拼多多客服聊天页，Cookie 优先，失效后再走账号密码登录。"""
        if "mms.pinduoduo.com/chat-merchant" in self._page.url and await self.is_logged_in():
            logger.info("[%s] Already on PDD chat page and logged in", self._shop_id)
            self._chat_frame = await self._find_chat_frame()
            return

        logger.info("[%s] Trying cookie-based login: navigating to %s", self._shop_id, PDD_CHAT_URL)
        try:
            await _wait(
                self._page.goto(PDD_CHAT_URL, wait_until="domcontentloaded", timeout=30000),
                timeout_seconds=35.0,
            )
        except Exception as exc:
            logger.warning("[%s] Navigation to chat URL failed: %s", self._shop_id, exc)

        try:
            await _wait(
                self._page.wait_for_load_state("load", timeout=15000),
                timeout_seconds=18.0,
            )
        except Exception:
            pass
        await _wait(self._page.wait_for_timeout(2000), timeout_seconds=4.0)

        if not await self._is_on_login_page():
            if await self.is_logged_in():
                logger.info("[%s] Cookie login successful!", self._shop_id)
                try:
                    await self._wait_for_selector("session_list", timeout_ms=15000)
                except (PlaywrightTimeoutError, TimeoutError):
                    logger.warning("[%s] Session list not found after cookie login", self._shop_id)
                await self.dismiss_popups()
                self._chat_frame = await self._find_chat_frame()
                return

            logger.info("[%s] On chat page but not fully logged in, will try credentials", self._shop_id)

        if await self._is_on_login_page():
            if username and password:
                logger.info("[%s] Cookie expired, falling back to username/password login", self._shop_id)
                login_ok = await self.auto_login(username, password)
                if login_ok:
                    if "chat-merchant" not in self._page.url.lower():
                        try:
                            await _wait(
                                self._page.goto(PDD_CHAT_URL, wait_until="domcontentloaded", timeout=30000),
                                timeout_seconds=35.0,
                            )
                            await _wait(self._page.wait_for_timeout(3000), timeout_seconds=5.0)
                        except Exception as exc:
                            logger.warning("[%s] Post-login navigation failed: %s", self._shop_id, exc)
                else:
                    logger.error("[%s] Auto-login failed", self._shop_id)
                    return
            else:
                logger.warning("[%s] On login page but no credentials provided, waiting for manual login", self._shop_id)

        try:
            await self._wait_for_selector("session_list", timeout_ms=15000)
            logger.info("[%s] PDD chat page loaded, session list visible", self._shop_id)
        except (PlaywrightTimeoutError, TimeoutError):
            logger.warning("[%s] Session list not found after navigation", self._shop_id)

        await self.dismiss_popups()
        self._chat_frame = await self._find_chat_frame()

    async def dismiss_popups(self, max_rounds: int = 3) -> int:
        """
        检测并关闭 PDD 商家后台的通知/推广弹窗。

        最多执行 max_rounds 轮（每轮检测所有已知弹窗类型），
        返回总共关闭的弹窗数量。
        """
        total_dismissed = 0
        dismiss_keys = ("popup_dismiss_today", "popup_dismiss_ok", "popup_close_icon")

        for round_num in range(max_rounds):
            dismissed_this_round = 0

            for key in dismiss_keys:
                try:
                    element = await self._query_selector(self._page, key)
                    if element is None:
                        continue

                    visible = await _wait(element.is_visible(), timeout_seconds=2.0)
                    if not visible:
                        continue

                    await _wait(element.click(), timeout_seconds=3.0)
                    dismissed_this_round += 1
                    total_dismissed += 1
                    logger.info(
                        "[%s] Dismissed popup (selector=%s, round=%d)",
                        self._shop_id,
                        key,
                        round_num + 1,
                    )
                    await _wait(self._page.wait_for_timeout(800), timeout_seconds=2.0)
                except Exception as exc:
                    logger.debug("[%s] Popup dismiss attempt failed for %s: %s", self._shop_id, key, exc)

            if dismissed_this_round == 0:
                break

        if total_dismissed > 0:
            logger.info("[%s] Total popups dismissed: %d", self._shop_id, total_dismissed)
        return total_dismissed

    async def _read_online_status_text(self) -> str:
        status_element = await self._query_selector(self._page, "online_status_text")
        if status_element is None:
            return ""
        try:
            return str(await _wait(status_element.inner_text(), timeout_seconds=2.0)).strip()
        except Exception:
            return ""

    async def detect_session_timeout(self) -> bool:
        timeout_hint = await self._query_selector(self._page, "session_timeout_hint")
        if timeout_hint is None:
            return False

        try:
            visible = await _wait(timeout_hint.is_visible(), timeout_seconds=2.0)
        except Exception:
            visible = False
        if not visible:
            return False

        refresh_button = await self._query_selector(self._page, "session_timeout_refresh_btn")
        if refresh_button is not None:
            try:
                await _wait(refresh_button.click(), timeout_seconds=3.0)
            except Exception:
                await _wait(
                    self._page.reload(wait_until="domcontentloaded"),
                    timeout_seconds=10.0,
                )
        else:
            await _wait(
                self._page.reload(wait_until="domcontentloaded"),
                timeout_seconds=10.0,
            )

        await _wait(self._page.wait_for_timeout(3000), timeout_seconds=5.0)
        return True

    async def ensure_online_status(self) -> bool:
        """
        检测客服是否处于在线状态，如果不是则尝试切换回在线。

        Returns:
            True 表示当前已在线或成功切回，False 表示检测或切换失败。
        """
        status_text = await self._read_online_status_text()
        if not status_text:
            logger.debug("[%s] Online status DOM not found, assuming online", self._shop_id)
            return True

        if "在线" in status_text:
            return True

        if "离线" not in status_text and "忙碌" not in status_text:
            logger.debug("[%s] Unrecognized online status text: %s", self._shop_id, status_text)
            return True

        switch_button = await self._query_selector(self._page, "online_switch_button")
        if switch_button is not None:
            try:
                await _wait(switch_button.click(), timeout_seconds=3.0)
                await _wait(self._page.wait_for_timeout(2000), timeout_seconds=4.0)
            except Exception:
                logger.debug("[%s] Failed to click online switch", self._shop_id, exc_info=True)

        refreshed_status_text = await self._read_online_status_text()
        if "在线" in refreshed_status_text:
            logger.info("[%s] Online status restored successfully", self._shop_id)
            return True

        await send_notification(
            "客服离线",
            f"店铺 {self._shop_id} 客服状态为离线，自动切换失败，请手动检查",
            event_key=f"{self._shop_id}:online_status_switch_failed",
        )
        return False

    async def auto_login(self, username: str, password: str, timeout_ms: int = 120000) -> bool:
        """
        自动登录拼多多商家后台。

        Returns:
            True 表示登录成功，False 表示超时或失败。
        """
        if not username or not password:
            logger.warning("[%s] Auto-login skipped because credentials are incomplete", self._shop_id)
            return False

        logger.info("[%s] Starting auto-login", self._shop_id)

        if not await self._is_on_login_page():
            logger.info("[%s] Navigating to login page: %s", self._shop_id, PDD_LOGIN_URL)
            try:
                await _wait(
                    self._page.goto(PDD_LOGIN_URL, wait_until="domcontentloaded", timeout=30000),
                    timeout_seconds=35.0,
                )
            except Exception as exc:
                logger.error("[%s] Failed to navigate to login page: %s", self._shop_id, exc)
                return False
            try:
                await _wait(
                    self._page.wait_for_load_state("load", timeout=15000),
                    timeout_seconds=18.0,
                )
            except Exception:
                logger.warning("[%s] Login page load state wait timed out", self._shop_id)

        try:
            await _wait(
                self._page.wait_for_load_state("load", timeout=15000),
                timeout_seconds=18.0,
            )
        except Exception:
            logger.warning("[%s] wait_for_load_state('load') timed out, continuing anyway", self._shop_id)
        await _wait(self._page.wait_for_timeout(1000), timeout_seconds=3.0)

        tab: ElementHandle | None = None
        try:
            tab = await self._wait_for_selector("login_tab_account", timeout_ms=15000)
        except (PlaywrightTimeoutError, TimeoutError):
            logger.warning("[%s] '账号登录' tab wait timed out, falling back to direct query", self._shop_id)
            try:
                tab = await self._query_selector(self._page, "login_tab_account")
            except Exception as exc:
                logger.warning("[%s] Failed to query login tab after wait timeout: %s", self._shop_id, exc)
        except Exception as exc:
            logger.warning("[%s] Failed to click login tab: %s", self._shop_id, exc)

        if tab is not None:
            try:
                await self._human_simulator.bezier_click(tab)
                logger.info("[%s] Clicked '账号登录' tab", self._shop_id)
                try:
                    await self._wait_for_selector("login_username", timeout_ms=8000)
                    logger.info("[%s] Account login form visible after tab click", self._shop_id)
                except (PlaywrightTimeoutError, TimeoutError):
                    logger.warning("[%s] Username field not visible after first tab click, retrying...", self._shop_id)
                    tab_retry = await self._query_selector(self._page, "login_tab_account")
                    if tab_retry is not None:
                        await self._human_simulator.bezier_click(tab_retry)
                        await _wait(self._page.wait_for_timeout(2000), timeout_seconds=4.0)
            except Exception as exc:
                logger.warning("[%s] Failed to click login tab: %s", self._shop_id, exc)
        else:
            logger.warning("[%s] '账号登录' tab not found after 15s wait", self._shop_id)

        try:
            username_input = await self._wait_for_selector("login_username", timeout_ms=15000)
            if username_input is None:
                logger.error("[%s] Username input (#usernameId) not found", self._shop_id)
                return False

            await _wait(username_input.click(), timeout_seconds=2.0)
            await _wait(self._page.keyboard.press("Control+a"), timeout_seconds=2.0)
            await self._human_simulator.simulate_typing(username_input, username)
            logger.info("[%s] Username entered", self._shop_id)
        except Exception as exc:
            logger.error("[%s] Failed to enter username: %s", self._shop_id, exc)
            return False

        try:
            password_input = await self._wait_for_selector("login_password", timeout_ms=10000)
            if password_input is None:
                logger.error("[%s] Password input (#passwordId) not found", self._shop_id)
                return False

            await _wait(password_input.click(), timeout_seconds=2.0)
            await _wait(self._page.keyboard.press("Control+a"), timeout_seconds=2.0)
            await self._human_simulator.simulate_typing(password_input, password)
            logger.info("[%s] Password entered", self._shop_id)
        except Exception as exc:
            logger.error("[%s] Failed to enter password: %s", self._shop_id, exc)
            return False

        try:
            login_btn = await self._wait_for_selector("login_button", timeout_ms=10000)
            if login_btn is None:
                logger.error("[%s] Login button not found", self._shop_id)
                return False

            await _wait(self._page.wait_for_timeout(500), timeout_seconds=2.0)
            await self._human_simulator.bezier_click(login_btn)
            logger.info("[%s] Login button clicked", self._shop_id)
        except Exception as exc:
            logger.error("[%s] Failed to click login button: %s", self._shop_id, exc)
            return False

        logger.info("[%s] Waiting for login result (captcha may appear)...", self._shop_id)
        max_wait_seconds = max(timeout_ms // 1000, 1)
        interval_seconds = 3.0
        elapsed_seconds = 0.0
        captcha_notified = False
        sms_notified = False

        while elapsed_seconds < max_wait_seconds:
            await _wait(
                self._page.wait_for_timeout(int(interval_seconds * 1000)),
                timeout_seconds=interval_seconds + 2.0,
            )
            elapsed_seconds += interval_seconds

            current_url = self._page.url.lower()
            if "login" not in current_url and "passport" not in current_url:
                logger.info("[%s] Login successful! Redirected to: %s", self._shop_id, self._page.url)
                return True

            captcha = await self._query_selector(self._page, "login_captcha_slider")
            if captcha is not None:
                if not captcha_notified:
                    captcha_notified = True
                    await send_notification(
                        "需要验证码",
                        f"店铺 {self._shop_id} 登录遇到滑块验证码，请手动处理",
                        event_key=f"{self._shop_id}:login_captcha_slider",
                    )
                if elapsed_seconds % 15 < interval_seconds:
                    logger.warning(
                        "[%s] Captcha detected, waiting for manual resolution... (%.0fs)",
                        self._shop_id,
                        elapsed_seconds,
                    )
                continue

            sms_input = await self._query_selector(self._page, "login_sms_input")
            if sms_input is not None:
                if not sms_notified:
                    sms_notified = True
                    await send_notification(
                        "需要短信验证码",
                        f"店铺 {self._shop_id} 登录需要短信验证码，请手动输入",
                        event_key=f"{self._shop_id}:login_sms_input",
                    )
                if elapsed_seconds % 15 < interval_seconds:
                    logger.warning(
                        "[%s] SMS verification required, waiting... (%.0fs)",
                        self._shop_id,
                        elapsed_seconds,
                    )
                continue

            if elapsed_seconds % 15 < interval_seconds:
                logger.info("[%s] Still on login page, waiting... (%.0fs)", self._shop_id, elapsed_seconds)

        logger.error("[%s] Login timeout after %ds", self._shop_id, max_wait_seconds)
        return False

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

        if self._chat_frame is None:
            self._chat_frame = await self._find_chat_frame()

        scope = self._chat_frame or self._page
        if await self._query_selector(scope, "message_container") is None:
            self._chat_frame = await self._find_chat_frame()
            scope = self._chat_frame or self._page

        messages: list[RawMessage] = []
        now = datetime.now().isoformat()
        all_items: list[tuple[ElementHandle, str]] = []
        for selector in (".buyer-item", ".seller-item", ".robot-item"):
            try:
                found = await _wait(scope.query_selector_all(selector), timeout_seconds=5.0)
            except Exception:
                continue
            sender = "buyer" if "buyer" in selector else "human"
            all_items.extend((item, sender) for item in found)

        for index, (item, sender) in enumerate(all_items):
            try:
                text_el = await self._query_selector(item, "message_text")
                if text_el is None:
                    continue

                content = (await _wait(text_el.inner_text())).strip()
                if not content:
                    continue

                index_el = await self._query_selector(item, "message_index")
                msg_index = ""
                if index_el is not None:
                    msg_index = (await _wait(index_el.get_attribute("index"))) or ""

                content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
                dedup_key = f"{self._shop_id}:{session_id}:{msg_index}:{content_hash}"
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
                await _wait(input_box.press("Control+Enter"), timeout_seconds=2.0)

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
        """多层检测是否已登录，不依赖 URL hash。"""
        try:
            current_url = self._page.url.lower()

            if "login" in current_url or "passport" in current_url:
                logger.info("[%s] Not logged in: on login/passport page", self._shop_id)
                return False

            if "chat-merchant" in current_url:
                element = await self._query_selector(self._page, "session_list")
                if element is not None:
                    return True

                try:
                    await self._wait_for_selector("session_item", timeout_ms=5000)
                    return True
                except (PlaywrightTimeoutError, TimeoutError):
                    pass

            if (
                "mms.pinduoduo.com" in current_url
                and "chat-merchant" not in current_url
                and "login" not in current_url
            ):
                return True

            return False
        except Exception as exc:
            logger.warning("[%s] Login check error: %s", self._shop_id, exc)
            return False

    async def wait_for_login(self, timeout_ms: int = 120000) -> bool:
        """等待用户手动登录。"""
        logger.info("Waiting for manual login...")
        if await self._wait_for_logged_in_element(timeout_ms=timeout_ms):
            self._chat_frame = await self._find_chat_frame()
            logger.info("Login detected")
            return True

        logger.error("Login timeout")
        return False
