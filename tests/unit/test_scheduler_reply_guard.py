from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.adapters import RawMessage, SessionInfo
from backend.services import scheduler


@pytest.mark.asyncio
async def test_process_session_skips_auto_reply_when_human_replied_after_latest_buyer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop_scheduler = scheduler.ShopScheduler()
    session_info = SessionInfo(session_id="session-1", buyer_id="buyer-1", buyer_name="买家A")
    buyer_old = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="在吗",
        sender="buyer",
        timestamp="2026-03-22T10:00:00",
        dedup_key="buyer-old",
    )
    buyer_latest = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="什么时候发货",
        sender="buyer",
        timestamp="2026-03-22T10:01:00",
        dedup_key="buyer-latest",
    )
    human_reply = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="今天会发出",
        sender="human",
        timestamp="2026-03-22T10:02:00",
        dedup_key="human-1",
    )

    class FakeAdapter:
        def __init__(self) -> None:
            self.sent_messages: list[tuple[str, str]] = []

        async def switch_to_session(self, session_id: str) -> None:
            assert session_id == "session-1"

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            assert session_id == "session-1"
            return [buyer_old, buyer_latest, human_reply]

        async def send_message(self, session_id: str, text: str) -> bool:
            self.sent_messages.append((session_id, text))
            return True

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            raise AssertionError("trigger_escalation should not be called")

    process_calls: list[tuple[str, bool]] = []

    async def fake_process_buyer_message(
        shop_id: str,
        raw_msg: RawMessage,
        llm_client: object,
        ai_enabled: bool = True,
    ) -> SimpleNamespace:
        assert shop_id == "shop-1"
        assert llm_client is not None
        process_calls.append((raw_msg.dedup_key, ai_enabled))
        return SimpleNamespace(action="stored", session_id="session-1")

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "process_buyer_message", fake_process_buyer_message)

    await shop_scheduler._process_session(
        "shop-1",
        fake_adapter,
        session_info,
        {"ai_enabled": True},
        object(),
    )

    assert process_calls == [("buyer-old", False), ("buyer-latest", False)]
    assert fake_adapter.sent_messages == []


@pytest.mark.asyncio
async def test_process_session_robot_reply_after_buyer_does_not_block_auto_reply(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop_scheduler = scheduler.ShopScheduler()
    session_info = SessionInfo(session_id="session-1", buyer_id="buyer-1", buyer_name="买家A")
    buyer_message = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="什么时候发货",
        sender="buyer",
        timestamp="2026-03-22T10:00:00",
        dedup_key="buyer-1",
    )
    robot_message = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="机器人占位回复",
        sender="robot",
        timestamp="2026-03-22T10:01:00",
        dedup_key="robot-1",
    )

    class FakeAdapter:
        def __init__(self) -> None:
            self.sent_messages: list[tuple[str, str]] = []

        async def switch_to_session(self, session_id: str) -> None:
            assert session_id == "session-1"

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            assert session_id == "session-1"
            return [buyer_message, robot_message]

        async def send_message(self, session_id: str, text: str) -> bool:
            self.sent_messages.append((session_id, text))
            return True

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            raise AssertionError("trigger_escalation should not be called")

    async def fake_process_buyer_message(
        shop_id: str,
        raw_msg: RawMessage,
        llm_client: object,
        ai_enabled: bool = True,
    ) -> SimpleNamespace:
        assert shop_id == "shop-1"
        assert raw_msg is buyer_message
        assert llm_client is not None
        assert ai_enabled is True
        return SimpleNamespace(action="reply", reply_text="今天发货", session_id="session-1")

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "process_buyer_message", fake_process_buyer_message)

    await shop_scheduler._process_session(
        "shop-1",
        fake_adapter,
        session_info,
        {"ai_enabled": True},
        object(),
    )

    assert fake_adapter.sent_messages == [("session-1", "今天发货")]
