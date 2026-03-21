from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.adapters.pdd import PddAdapter


def _make_adapter() -> tuple[PddAdapter, object]:
    page = type("PageDouble", (), {})()
    page.url = "https://mms.pinduoduo.com/chat-merchant/#/"
    page.frames = []
    page.wait_for_timeout = AsyncMock()
    page.reload = AsyncMock()
    adapter = PddAdapter(page, "shop-1")
    return adapter, page


@pytest.mark.asyncio
async def test_detect_session_timeout_clicks_refresh_button_when_visible() -> None:
    adapter, page = _make_adapter()
    hint = MagicMock()
    hint.is_visible = AsyncMock(return_value=True)
    refresh_button = MagicMock()
    refresh_button.click = AsyncMock()

    async def mock_query_selector(_: object, key: str) -> object | None:
        if key == "session_timeout_hint":
            return hint
        if key == "session_timeout_refresh_btn":
            return refresh_button
        return None

    adapter._query_selector = AsyncMock(side_effect=mock_query_selector)  # type: ignore[method-assign]

    result = await adapter.detect_session_timeout()

    assert result is True
    refresh_button.click.assert_awaited_once()
    page.reload.assert_not_awaited()
    page.wait_for_timeout.assert_awaited_once_with(3000)


@pytest.mark.asyncio
async def test_detect_session_timeout_reloads_when_refresh_button_missing() -> None:
    adapter, page = _make_adapter()
    hint = MagicMock()
    hint.is_visible = AsyncMock(return_value=True)

    async def mock_query_selector(_: object, key: str) -> object | None:
        if key == "session_timeout_hint":
            return hint
        return None

    adapter._query_selector = AsyncMock(side_effect=mock_query_selector)  # type: ignore[method-assign]

    result = await adapter.detect_session_timeout()

    assert result is True
    page.reload.assert_awaited_once_with(wait_until="domcontentloaded")
    page.wait_for_timeout.assert_awaited_once_with(3000)


@pytest.mark.asyncio
async def test_ensure_online_status_clicks_switch_and_recovers_online() -> None:
    adapter, page = _make_adapter()
    offline_status = MagicMock()
    offline_status.inner_text = AsyncMock(return_value="离线")
    online_status = MagicMock()
    online_status.inner_text = AsyncMock(return_value="在线")
    switch_button = MagicMock()
    switch_button.click = AsyncMock()
    status_checks = 0

    async def mock_query_selector(_: object, key: str) -> object | None:
        nonlocal status_checks
        if key == "online_status_text":
            status_checks += 1
            return offline_status if status_checks == 1 else online_status
        if key == "online_switch_button":
            return switch_button
        return None

    adapter._query_selector = AsyncMock(side_effect=mock_query_selector)  # type: ignore[method-assign]

    result = await adapter.ensure_online_status()

    assert result is True
    switch_button.click.assert_awaited_once()
    page.wait_for_timeout.assert_awaited_once_with(2000)


@pytest.mark.asyncio
async def test_ensure_online_status_notifies_when_switch_fails() -> None:
    adapter, _ = _make_adapter()
    offline_status = MagicMock()
    offline_status.inner_text = AsyncMock(return_value="离线")

    async def mock_query_selector(_: object, key: str) -> object | None:
        if key == "online_status_text":
            return offline_status
        return None

    adapter._query_selector = AsyncMock(side_effect=mock_query_selector)  # type: ignore[method-assign]

    with patch("backend.adapters.pdd.send_notification", new=AsyncMock(return_value=True)) as mock_notify:
        result = await adapter.ensure_online_status()

    assert result is False
    mock_notify.assert_awaited_once()
