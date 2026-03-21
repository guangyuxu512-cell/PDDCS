from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from backend.services import notifier


class _FakeResponse:
    def __init__(self, should_fail: bool = False) -> None:
        self._should_fail = should_fail

    def raise_for_status(self) -> None:
        if self._should_fail:
            raise RuntimeError("webhook failed")


@pytest.fixture(autouse=True)
def clear_notification_state() -> None:
    notifier._NOTIFICATION_RESERVATIONS.clear()


@pytest.mark.asyncio
@pytest.mark.parametrize("webhook_type", ["feishu", "dingtalk", "wecom", "generic"])
async def test_send_notification_builds_expected_payload(
    monkeypatch: pytest.MonkeyPatch,
    webhook_type: str,
) -> None:
    post_calls: list[dict[str, Any]] = []

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            post_calls.append({"url": url, "json": json, "timeout": self.timeout})
            return _FakeResponse()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        notifier,
        "get_settings",
        lambda: SimpleNamespace(notify_webhook_url="https://example.com/hook", notify_webhook_type=webhook_type),
    )
    monkeypatch.setattr(notifier.httpx, "AsyncClient", FakeAsyncClient)

    sent = await notifier.send_notification("标题", "内容", level="error")

    assert sent is True
    assert post_calls[0]["url"] == "https://example.com/hook"

    payload = post_calls[0]["json"]
    if webhook_type == "feishu":
        assert payload == {
            "msg_type": "interactive",
            "card": {
                "header": {"title": {"tag": "plain_text", "content": "标题"}},
                "elements": [
                    {
                        "tag": "div",
                        "text": {"tag": "plain_text", "content": "内容"},
                    }
                ],
            },
        }
        return

    if webhook_type in {"dingtalk", "wecom"}:
        assert payload == {
            "msgtype": "text",
            "text": {"content": "[标题] 内容"},
        }
        return

    assert payload["title"] == "标题"
    assert payload["content"] == "内容"
    assert payload["level"] == "error"
    assert payload["timestamp"]


@pytest.mark.asyncio
async def test_send_notification_suppresses_duplicate_events_within_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post_calls: list[dict[str, Any]] = []

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            post_calls.append({"url": url, "json": json, "timeout": self.timeout})
            return _FakeResponse()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        notifier,
        "get_settings",
        lambda: SimpleNamespace(notify_webhook_url="https://example.com/hook", notify_webhook_type="generic"),
    )
    monkeypatch.setattr(notifier.httpx, "AsyncClient", FakeAsyncClient)

    first = await notifier.send_notification("标题", "内容", event_key="shop-1:event")
    second = await notifier.send_notification("标题", "内容", event_key="shop-1:event")

    assert first is True
    assert second is False
    assert len(post_calls) == 1


@pytest.mark.asyncio
async def test_send_notification_releases_reservation_when_request_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_count = 0

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            self.timeout = timeout

        async def post(self, url: str, json: dict[str, Any]) -> _FakeResponse:
            nonlocal call_count
            del url, json, self.timeout
            call_count += 1
            if call_count == 1:
                raise RuntimeError("network failed")
            return _FakeResponse()

        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(
        notifier,
        "get_settings",
        lambda: SimpleNamespace(notify_webhook_url="https://example.com/hook", notify_webhook_type="generic"),
    )
    monkeypatch.setattr(notifier.httpx, "AsyncClient", FakeAsyncClient)

    first = await notifier.send_notification("标题", "内容", event_key="shop-1:event")
    second = await notifier.send_notification("标题", "内容", event_key="shop-1:event")

    assert first is False
    assert second is True
    assert call_count == 2
