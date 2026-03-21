from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.adapters.pdd import PddAdapter


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

    async def query_selector(self, selector: str) -> FakeElement | None:
        return self._selectors.get(selector)

    async def query_selector_all(self, selector: str) -> list[FakeElement]:
        return list(self._selector_lists.get(selector, []))

    async def inner_text(self) -> str:
        return self._text

    async def get_attribute(self, name: str) -> str | None:
        return self._attrs.get(name)


class FakeScope:
    def __init__(
        self,
        *,
        selectors: dict[str, FakeElement] | None = None,
        selector_lists: dict[str, list[FakeElement]] | None = None,
    ) -> None:
        self._selectors = selectors or {}
        self._selector_lists = selector_lists or {}
        self.frames: list[FakeScope] = []

    async def query_selector(self, selector: str) -> FakeElement | None:
        return self._selectors.get(selector)

    async def query_selector_all(self, selector: str) -> list[FakeElement]:
        return list(self._selector_lists.get(selector, []))


def _session_item(
    *,
    session_id: str,
    buyer_name: str,
    last_message: str,
    countdown_text: str = "",
    skipped: bool = False,
) -> FakeElement:
    box_classes = "chat-item-box un-watch" if skipped else "chat-item-box"
    box = FakeElement(attrs={"class": box_classes, "data-random": session_id})
    countdown = FakeElement(text=countdown_text) if countdown_text else None
    selectors = {
        "div.chat-item-box": box,
        "span.nickname-span": FakeElement(text=buyer_name),
        "p.chat-message-content": FakeElement(text=last_message),
    }
    if countdown is not None:
        selectors["p.chat-unreply-time"] = countdown
    return FakeElement(selectors=selectors)


def _message_item(
    *,
    sender: str,
    text: str,
    index: str,
) -> FakeElement:
    selectors: dict[str, FakeElement] = {
        ".msg-content-box": FakeElement(text=text),
        ".msg-content": FakeElement(attrs={"index": index}),
    }
    if sender == "buyer":
        selectors[".buyer-item"] = FakeElement()
    elif sender == "human":
        selectors[".seller-item"] = FakeElement()
    elif sender == "robot":
        selectors[".robot-item"] = FakeElement()
    elif sender == "system":
        selectors[".system-msg-31"] = FakeElement()
        selectors[".content-box"] = FakeElement(text=text)
    return FakeElement(selectors=selectors)


@pytest.mark.asyncio
async def test_get_session_list_prioritizes_timeout_then_pending_and_skips_unwatch() -> None:
    timeout_item = _session_item(
        session_id="timeout-1",
        buyer_name="超时买家",
        last_message="请尽快回复",
    )
    pending_slow = _session_item(
        session_id="pending-50",
        buyer_name="慢超时",
        last_message="还有 50 秒",
        countdown_text="50秒后超时",
    )
    pending_fast = _session_item(
        session_id="pending-12",
        buyer_name="快超时",
        last_message="还有 12 秒",
        countdown_text="12秒后超时",
    )
    skipped_item = _session_item(
        session_id="skipped-1",
        buyer_name="应跳过",
        last_message="机器人已处理",
        countdown_text="9秒后超时",
        skipped=True,
    )
    page = FakeScope(
        selector_lists={
            "ul.timeout-unreply li.chat-item": [timeout_item],
            "ul.five-minute li.chat-item": [pending_slow, pending_fast, skipped_item],
        }
    )
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=MagicMock())

    sessions = await adapter.get_session_list()

    assert [session.session_id for session in sessions] == ["timeout-1", "pending-12", "pending-50"]
    assert [session.buyer_name for session in sessions] == ["超时买家", "快超时", "慢超时"]
    assert [session.remaining_seconds for session in sessions] == [0, 12, 50]
    assert sessions[0].is_timeout is True
    assert sessions[1].session_selector == 'div.chat-item-box[data-random="pending-12"]'


@pytest.mark.asyncio
async def test_fetch_messages_preserves_dom_order_and_classifies_roles() -> None:
    ordered_items = [
        _message_item(sender="buyer", text="买家消息", index="101"),
        _message_item(sender="human", text="人工回复", index="102"),
        _message_item(sender="robot", text="机器人回复", index="103"),
        _message_item(sender="system", text="恢复接待", index="104"),
    ]
    page = FakeScope(
        selectors={".merchantMessage": FakeElement()},
        selector_lists={"li.onemsg": ordered_items},
    )
    adapter = PddAdapter(page=page, shop_id="shop-1", human_simulator=MagicMock())
    adapter._current_session_id = "session-1"
    adapter._chat_frame = page
    adapter._session_names["session-1"] = "买家甲"

    messages = await adapter.fetch_messages("session-1")

    assert [message.sender for message in messages] == ["buyer", "human", "robot", "system"]
    assert [message.message_type for message in messages] == ["buyer", "human", "robot", "system"]
    assert [message.content for message in messages] == ["买家消息", "人工回复", "机器人回复", "恢复接待"]
    assert messages[0].dedup_key.startswith("shop-1:session-1:101:")
    assert messages[3].buyer_name == "买家甲"
