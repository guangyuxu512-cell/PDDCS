"""PDD 适配器单元测试，仅测试数据结构和辅助逻辑。"""

from __future__ import annotations

import hashlib

import pytest

from backend.adapters.base import RawMessage, SessionInfo
from backend.adapters.pdd import PDD_CHAT_URL, SELECTORS, PddAdapter
from backend.adapters.selector_config import SelectorConfig
from backend.engines.playwright_engine import PlaywrightEngine


class FakeElement:
    def __init__(
        self,
        *,
        text: str = "",
        attrs: dict[str, str] | None = None,
        selectors: dict[str, FakeElement] | None = None,
        selector_lists: dict[str, list[FakeElement]] | None = None,
    ) -> None:
        self._text = text
        self._attrs = attrs or {}
        self._selectors = selectors or {}
        self._selector_lists = selector_lists or {}
        self.pressed: list[str] = []
        self.clicked = False

    async def query_selector(self, selector: str) -> FakeElement | None:
        return self._selectors.get(selector)

    async def query_selector_all(self, selector: str) -> list[FakeElement]:
        return list(self._selector_lists.get(selector, []))

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)

    async def press(self, key: str) -> None:
        self.pressed.append(key)

    async def click(self) -> None:
        self.clicked = True


class FakeKeyboard:
    def __init__(self) -> None:
        self.pressed: list[str] = []

    async def press(self, key: str) -> None:
        self.pressed.append(key)


class FakeScope:
    def __init__(
        self,
        *,
        url: str = "",
        selectors: dict[str, FakeElement] | None = None,
        selector_lists: dict[str, list[FakeElement]] | None = None,
        wait_selectors: dict[str, FakeElement] | None = None,
        frames: list[FakeScope] | None = None,
        final_url: str | None = None,
        url_after_timeout_call: dict[int, str] | None = None,
    ) -> None:
        self.url = url
        self.frames = frames or []
        self._selectors = selectors or {}
        self._selector_lists = selector_lists or {}
        self._wait_selectors = wait_selectors or {}
        self._final_url = final_url
        self._url_after_timeout_call = url_after_timeout_call or {}
        self.goto_calls: list[tuple[str, str, int]] = []
        self.wait_for_timeout_calls: list[int] = []
        self.keyboard = FakeKeyboard()

    async def query_selector(self, selector: str) -> FakeElement | None:
        return self._selectors.get(selector)

    async def query_selector_all(self, selector: str) -> list[FakeElement]:
        return list(self._selector_lists.get(selector, []))

    async def wait_for_selector(self, selector: str, timeout: int) -> FakeElement:
        del timeout
        handle = self._wait_selectors.get(selector)
        if handle is None:
            raise TimeoutError(f"selector not found: {selector}")
        return handle

    async def goto(self, url: str, wait_until: str, timeout: int) -> None:
        self.goto_calls.append((url, wait_until, timeout))
        self.url = self._final_url or url

    async def wait_for_timeout(self, timeout_ms: int) -> None:
        self.wait_for_timeout_calls.append(timeout_ms)
        next_url = self._url_after_timeout_call.get(len(self.wait_for_timeout_calls))
        if next_url is not None:
            self.url = next_url


class FakeHumanSimulator:
    def __init__(self) -> None:
        self.typed: list[tuple[object, str]] = []
        self.clicked: list[object] = []

    async def simulate_typing(self, target: object, text: str) -> None:
        self.typed.append((target, text))

    async def bezier_click(self, target: object) -> None:
        self.clicked.append(target)


def test_raw_message_fields() -> None:
    message = RawMessage(
        session_id="buyer1",
        buyer_id="buyer1",
        buyer_name="张三",
        content="你好",
        sender="buyer",
        timestamp="2026-03-19T06:00:00",
        dedup_key="shop1:buyer1:0:abc123",
    )
    assert message.sender == "buyer"
    assert message.dedup_key.startswith("shop1:")


def test_session_info_fields() -> None:
    info = SessionInfo(
        session_id="buyer1",
        buyer_id="buyer1",
        buyer_name="张三",
        last_message="你好",
        unread=True,
    )
    assert info.unread is True


def test_selectors_not_empty() -> None:
    for key, value in SELECTORS.items():
        assert isinstance(value, SelectorConfig), f"Selector '{key}' is not wrapped by SelectorConfig"
        assert value.primary, f"Selector '{key}' primary selector is empty"
        assert all(selector for selector in value.all()), f"Selector '{key}' contains empty fallback values"
    assert SELECTORS["login_tab_account"].primary == ".login-tab div:has-text('账号登录')"
    assert SELECTORS["login_username"].primary == "#usernameId"
    assert SELECTORS["login_password"].primary == "#passwordId"
    assert SELECTORS["login_button"].primary == "button:has-text('登录')"
    assert SELECTORS["login_captcha_slider"].primary == ".captcha-container"
    assert SELECTORS["login_sms_input"].primary == "input[placeholder='请输入短信验证码']"
    assert SELECTORS["session_item"].primary == "li.chat-item"
    assert SELECTORS["message_container"].primary == ".merchantMessage"
    assert SELECTORS["input_box"].primary == "textarea#replyTextarea"


def test_chat_url() -> None:
    assert PDD_CHAT_URL == "https://mms.pinduoduo.com/chat-merchant/#/"


def test_dedup_key_generation() -> None:
    content = "你好，我要退款"
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    dedup_key = f"shop1:buyer1:msg-1:{content_hash}"
    assert content_hash in dedup_key
    assert ":msg-1:" in dedup_key
    assert len(dedup_key) > 0


def test_playwright_engine_default_state() -> None:
    engine = PlaywrightEngine()
    assert engine.is_running is False


@pytest.mark.asyncio
async def test_playwright_engine_requires_start_before_creating_context() -> None:
    engine = PlaywrightEngine()
    with pytest.raises(RuntimeError):
        await engine.get_or_create_context("shop-1")


@pytest.mark.asyncio
async def test_find_chat_frame_prefers_child_frame_when_message_container_only_exists_in_frame() -> None:
    child_frame = FakeScope(
        url="https://mms.pinduoduo.com/chat-merchant/frame",
        selectors={".merchantMessage": FakeElement()},
    )
    page = FakeScope(url="https://mms.pinduoduo.com/chat-merchant/#/", frames=[child_frame])
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=FakeHumanSimulator())

    chat_scope = await adapter._find_chat_frame()

    assert chat_scope is child_frame


@pytest.mark.asyncio
async def test_fetch_messages_uses_chat_frame_and_message_index_for_dedup() -> None:
    buyer_item = FakeElement(
        selectors={
            ".msg-content-box": FakeElement(text="买家消息"),
            ".msg-content": FakeElement(attrs={"index": "101"}),
        },
    )
    seller_item = FakeElement(
        selectors={
            ".msg-content-box": FakeElement(text="客服回复"),
            ".msg-content": FakeElement(attrs={"index": "102"}),
        },
    )
    chat_frame = FakeScope(
        url="https://mms.pinduoduo.com/chat-merchant/frame",
        selectors={".merchantMessage": FakeElement()},
        selector_lists={
            ".buyer-item": [buyer_item],
            ".seller-item": [seller_item],
            ".robot-item": [],
        },
    )
    page = FakeScope(url="https://mms.pinduoduo.com/chat-merchant/#/", frames=[chat_frame])
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=FakeHumanSimulator())
    adapter._current_session_id = "buyer-1"
    adapter._chat_frame = chat_frame

    messages = await adapter.fetch_messages("buyer-1")

    assert [message.sender for message in messages] == ["buyer", "human"]
    assert messages[0].dedup_key.startswith("shop-1:buyer-1:101:")
    assert messages[1].dedup_key.startswith("shop-1:buyer-1:102:")


@pytest.mark.asyncio
async def test_send_message_uses_ctrl_enter_when_send_button_missing() -> None:
    input_box = FakeElement()
    page = FakeScope(
        url="https://mms.pinduoduo.com/chat-merchant/#/",
        wait_selectors={"textarea#replyTextarea": input_box},
    )
    human_simulator = FakeHumanSimulator()
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=human_simulator)
    adapter._current_session_id = "buyer-1"

    sent = await adapter.send_message("buyer-1", "你好")

    assert sent is True
    assert human_simulator.typed == [(input_box, "你好")]
    assert human_simulator.clicked == []
    assert input_box.pressed == ["Control+Enter"]


@pytest.mark.asyncio
async def test_auto_login_uses_account_login_selectors_and_waits_for_chat_list() -> None:
    account_tab = FakeElement()
    username_input = FakeElement()
    password_input = FakeElement()
    login_button = FakeElement()
    page = FakeScope(
        url="https://mms.pinduoduo.com/login/",
        selectors={".login-tab div:has-text('账号登录')": account_tab},
        wait_selectors={
            "#usernameId": username_input,
            "#passwordId": password_input,
            "button:has-text('登录')": login_button,
        },
        url_after_timeout_call={4: "https://mms.pinduoduo.com/chat-merchant/#/"},
    )
    human_simulator = FakeHumanSimulator()
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=human_simulator)

    logged_in = await adapter.auto_login("seller", "secret")

    assert logged_in is True
    assert human_simulator.clicked == [account_tab, login_button]
    assert human_simulator.typed == [(username_input, "seller"), (password_input, "secret")]
    assert page.keyboard.pressed == ["Control+a", "Control+a"]


@pytest.mark.asyncio
async def test_navigate_to_chat_uses_auto_login_when_chat_list_is_missing() -> None:
    page = FakeScope(
        url="https://mms.pinduoduo.com/login/",
        final_url="https://mms.pinduoduo.com/login/",
    )
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=FakeHumanSimulator())
    auto_login_calls: list[tuple[str, str, int]] = []

    async def fake_auto_login(username: str, password: str, timeout_ms: int = 120000) -> bool:
        auto_login_calls.append((username, password, timeout_ms))
        page.url = "https://mms.pinduoduo.com/chat-merchant/#/"
        return True
    adapter.auto_login = fake_auto_login  # type: ignore[method-assign]

    await adapter.navigate_to_chat("seller", "secret")

    assert page.goto_calls == [(PDD_CHAT_URL, "domcontentloaded", 30000)]
    assert auto_login_calls == [("seller", "secret", 120000)]


@pytest.mark.asyncio
async def test_wait_for_login_returns_false_when_chat_list_never_appears() -> None:
    page = FakeScope(url="https://mms.pinduoduo.com/login/")
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=FakeHumanSimulator())

    logged_in = await adapter.wait_for_login(timeout_ms=1000)

    assert logged_in is False
