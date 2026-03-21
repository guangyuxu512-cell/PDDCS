from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from backend.adapters.pdd import PDD_CHAT_URL, PDD_LOGIN_URL, PddAdapter


def _make_adapter(url: str = "https://mms.pinduoduo.com/chat-merchant/#/") -> tuple[PddAdapter, object, MagicMock]:
    page = type("PageDouble", (), {})()
    state = {"url": url, "wait_calls": 0}

    def _get_url() -> str:
        return state["url"]

    async def _wait_for_timeout(_: int) -> None:
        state["wait_calls"] += 1
        if state["wait_calls"] >= 4 and "login" in state["url"]:
            state["url"] = PDD_CHAT_URL

    type(page).url = PropertyMock(side_effect=_get_url)
    page.frames = []
    page.goto = AsyncMock()
    page.query_selector = AsyncMock(return_value=None)
    page.query_selector_all = AsyncMock(return_value=[])
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError)
    page.wait_for_load_state = AsyncMock()
    page.wait_for_timeout = AsyncMock(side_effect=_wait_for_timeout)
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()

    simulator = MagicMock()
    simulator.bezier_click = AsyncMock()
    simulator.simulate_typing = AsyncMock()

    adapter = PddAdapter(page, "shop-test", simulator)
    return adapter, page, simulator


class TestIsLoggedIn:
    @pytest.mark.asyncio
    async def test_on_login_page_returns_false(self) -> None:
        adapter, _, _ = _make_adapter(PDD_LOGIN_URL)

        assert await adapter.is_logged_in() is False

    @pytest.mark.asyncio
    async def test_on_chat_page_with_session_list_returns_true(self) -> None:
        adapter, page, _ = _make_adapter(PDD_CHAT_URL)
        page.query_selector = AsyncMock(return_value=MagicMock())

        assert await adapter.is_logged_in() is True

    @pytest.mark.asyncio
    async def test_on_chat_page_without_session_elements_returns_false(self) -> None:
        adapter, page, _ = _make_adapter(PDD_CHAT_URL)
        page.query_selector = AsyncMock(return_value=None)
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError)

        assert await adapter.is_logged_in() is False


class TestAutoLogin:
    @pytest.mark.asyncio
    async def test_auto_login_success(self) -> None:
        adapter, page, simulator = _make_adapter(PDD_LOGIN_URL)

        tab = MagicMock()
        username_input = MagicMock()
        username_input.click = AsyncMock()
        password_input = MagicMock()
        password_input.click = AsyncMock()
        login_button = MagicMock()

        async def wait_for_selector(selector: str, timeout: int) -> object:
            del timeout
            if selector == ".login-tab div:has-text('账号登录')":
                return tab
            if selector == "#usernameId":
                return username_input
            if selector == "#passwordId":
                return password_input
            if selector == "button:has-text('登录')":
                return login_button
            raise TimeoutError(selector)

        page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)

        result = await adapter.auto_login("testuser", "testpass")

        assert result is True
        assert simulator.simulate_typing.call_count == 2
        assert simulator.bezier_click.call_count >= 2
        assert simulator.bezier_click.await_args_list[0].args == (tab,)
        assert page.keyboard.press.await_args_list[0].args == ("Control+a",)
        assert page.keyboard.press.await_args_list[1].args == ("Control+a",)
        assert page.wait_for_load_state.await_count >= 1

    @pytest.mark.asyncio
    async def test_auto_login_username_not_found(self) -> None:
        adapter, page, _ = _make_adapter(PDD_LOGIN_URL)

        async def query_selector(selector: str) -> object | None:
            if selector == ".login-tab div:has-text('账号登录')":
                return MagicMock()
            return None

        async def wait_for_selector(selector: str, timeout: int) -> object | None:
            if selector == ".login-tab div:has-text('账号登录')":
                return MagicMock()
            if selector == "#usernameId":
                raise TimeoutError(selector)
            return MagicMock()

        page.query_selector = AsyncMock(side_effect=query_selector)
        page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)

        result = await adapter.auto_login("user", "pass")

        assert result is False
        assert any(
            call.args == ("#usernameId",) and call.kwargs["timeout"] == 15000
            for call in page.wait_for_selector.await_args_list
        )

    @pytest.mark.asyncio
    async def test_auto_login_waits_for_tab_before_clicking(self) -> None:
        adapter, _, simulator = _make_adapter(PDD_LOGIN_URL)

        tab = MagicMock()
        username_input = MagicMock()
        username_input.click = AsyncMock()
        password_input = MagicMock()
        password_input.click = AsyncMock()
        login_button = MagicMock()
        wait_calls: list[tuple[str, int]] = []

        async def mock_wait_for_selector(selector_key: str, timeout_ms: int) -> object | None:
            wait_calls.append((selector_key, timeout_ms))
            if selector_key == "login_tab_account":
                return tab
            if selector_key == "login_username":
                return username_input
            if selector_key == "login_password":
                return password_input
            if selector_key == "login_button":
                return login_button
            raise AssertionError(selector_key)

        adapter._wait_for_selector = mock_wait_for_selector  # type: ignore[method-assign]
        adapter._query_selector = AsyncMock(return_value=None)  # type: ignore[method-assign]

        result = await adapter.auto_login("testuser", "testpass")

        assert result is True
        assert wait_calls[0] == ("login_tab_account", 15000)
        assert ("login_username", 8000) in wait_calls
        assert ("login_username", 15000) in wait_calls
        assert ("login_password", 10000) in wait_calls
        assert ("login_button", 10000) in wait_calls
        assert simulator.bezier_click.await_args_list[0].args == (tab,)
        assert not any(
            len(call.args) > 1 and call.args[1] == "login_tab_account"
            for call in adapter._query_selector.await_args_list
        )

    @pytest.mark.asyncio
    async def test_auto_login_retries_tab_click_when_username_not_visible(self) -> None:
        adapter, _, simulator = _make_adapter(PDD_LOGIN_URL)

        tab = MagicMock()
        retry_tab = MagicMock()
        username_input = MagicMock()
        username_input.click = AsyncMock()
        password_input = MagicMock()
        password_input.click = AsyncMock()
        login_button = MagicMock()

        async def mock_wait_for_selector(selector_key: str, timeout_ms: int) -> object | None:
            if selector_key == "login_tab_account":
                return tab
            if selector_key == "login_username" and timeout_ms == 8000:
                raise TimeoutError("login form still hidden")
            if selector_key == "login_username" and timeout_ms == 15000:
                return username_input
            if selector_key == "login_password":
                return password_input
            if selector_key == "login_button":
                return login_button
            raise AssertionError((selector_key, timeout_ms))

        async def mock_query_selector(_: object, selector_key: str) -> object | None:
            if selector_key == "login_tab_account":
                return retry_tab
            return None

        adapter._wait_for_selector = mock_wait_for_selector  # type: ignore[method-assign]
        adapter._query_selector = AsyncMock(side_effect=mock_query_selector)  # type: ignore[method-assign]

        result = await adapter.auto_login("testuser", "testpass")

        assert result is True
        assert simulator.bezier_click.await_args_list[0].args == (tab,)
        assert simulator.bezier_click.await_args_list[1].args == (retry_tab,)
        assert any(
            len(call.args) > 1 and call.args[1] == "login_tab_account"
            for call in adapter._query_selector.await_args_list
        )


class TestNavigateToChatWithLogin:
    @pytest.mark.asyncio
    async def test_redirected_to_login_triggers_auto_login(self) -> None:
        adapter, page, _ = _make_adapter("about:blank")
        state = {"url": "about:blank"}
        type(page).url = PropertyMock(side_effect=lambda: state["url"])

        async def goto(url: str, wait_until: str, timeout: int) -> None:
            assert wait_until == "domcontentloaded"
            assert timeout == 30000
            state["url"] = PDD_LOGIN_URL if url == PDD_CHAT_URL else url

        page.goto = AsyncMock(side_effect=goto)
        page.wait_for_timeout = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError)

        with patch.object(adapter, "auto_login", new_callable=AsyncMock, return_value=True) as mock_login:
            async def after_login(username: str, password: str) -> bool:
                state["url"] = PDD_CHAT_URL
                return True

            mock_login.side_effect = after_login
            with patch.object(adapter, "_find_chat_frame", new_callable=AsyncMock, return_value=page):
                await adapter.navigate_to_chat(username="user", password="pass")

        mock_login.assert_awaited_once_with("user", "pass")
        assert page.goto.await_args_list[0].args[0] == PDD_CHAT_URL

    @pytest.mark.asyncio
    async def test_no_credentials_does_not_auto_login(self) -> None:
        adapter, page, _ = _make_adapter("about:blank")
        state = {"url": "about:blank"}
        type(page).url = PropertyMock(side_effect=lambda: state["url"])

        async def goto(url: str, wait_until: str, timeout: int) -> None:
            del wait_until, timeout
            state["url"] = PDD_LOGIN_URL if url == PDD_CHAT_URL else url

        page.goto = AsyncMock(side_effect=goto)
        page.wait_for_timeout = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=TimeoutError)

        with patch.object(adapter, "auto_login", new_callable=AsyncMock) as mock_login:
            with patch.object(adapter, "_find_chat_frame", new_callable=AsyncMock, return_value=page):
                await adapter.navigate_to_chat()

        mock_login.assert_not_awaited()
