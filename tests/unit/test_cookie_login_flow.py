from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.adapters.pdd import PDD_CHAT_URL, PDD_LOGIN_URL, PddAdapter


def _make_adapter(url: str = "about:blank") -> tuple[PddAdapter, object]:
    page = type("PageDouble", (), {})()
    page.url = url
    page.frames = []
    page.goto = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError)
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()

    simulator = MagicMock()
    simulator.bezier_click = AsyncMock()
    simulator.simulate_typing = AsyncMock()

    return PddAdapter(page, "test-shop", simulator), page


@pytest.mark.asyncio
async def test_cookie_login_skips_credentials_when_valid() -> None:
    """Cookie 有效时不应调用 auto_login。"""
    adapter, page = _make_adapter(PDD_CHAT_URL)
    adapter.is_logged_in = AsyncMock(return_value=True)
    adapter.auto_login = AsyncMock()
    adapter._find_chat_frame = AsyncMock(return_value=page)

    await adapter.navigate_to_chat(username="user", password="pass")

    page.goto.assert_not_awaited()
    adapter.auto_login.assert_not_awaited()
    adapter._find_chat_frame.assert_awaited_once()


@pytest.mark.asyncio
async def test_cookie_expired_falls_back_to_credentials() -> None:
    """Cookie 失效时应回退到账号密码登录。"""
    adapter, page = _make_adapter()
    adapter.auto_login = AsyncMock(return_value=True)
    adapter.dismiss_popups = AsyncMock(return_value=0)
    adapter._find_chat_frame = AsyncMock(return_value=page)
    adapter._wait_for_selector = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]

    async def goto(url: str, wait_until: str, timeout: int) -> None:
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        if page.url == "about:blank":
            page.url = PDD_LOGIN_URL
            return
        page.url = url

    page.goto = AsyncMock(side_effect=goto)

    await adapter.navigate_to_chat(username="user", password="pass")

    assert page.goto.await_args_list[0].args[0] == PDD_CHAT_URL
    adapter.auto_login.assert_awaited_once_with("user", "pass")
    assert page.goto.await_count == 2
    assert page.url == PDD_CHAT_URL


@pytest.mark.asyncio
async def test_no_credentials_no_cookie_waits_for_manual() -> None:
    """无账号密码且无 Cookie 时应等待手动登录。"""
    adapter, page = _make_adapter()
    adapter.auto_login = AsyncMock()
    adapter.dismiss_popups = AsyncMock(return_value=0)
    adapter._find_chat_frame = AsyncMock(return_value=page)
    adapter._wait_for_selector = AsyncMock(side_effect=TimeoutError)  # type: ignore[method-assign]

    async def goto(url: str, wait_until: str, timeout: int) -> None:
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        page.url = PDD_LOGIN_URL

    page.goto = AsyncMock(side_effect=goto)

    await adapter.navigate_to_chat(username="", password="")

    assert page.goto.await_args_list[0].args[0] == PDD_CHAT_URL
    adapter.auto_login.assert_not_awaited()
    adapter.dismiss_popups.assert_awaited_once()
