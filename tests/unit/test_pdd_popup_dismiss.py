from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.adapters.pdd import PDD_CHAT_URL, PddAdapter
from backend.services import scheduler


def _make_adapter(url: str = PDD_CHAT_URL) -> tuple[PddAdapter, object]:
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

    adapter = PddAdapter(page, "test-shop")
    return adapter, page


@pytest.mark.asyncio
async def test_dismiss_popups_clicks_visible_elements() -> None:
    adapter, page = _make_adapter()
    element = MagicMock()
    element.is_visible = AsyncMock(return_value=True)
    element.click = AsyncMock()
    call_count = 0

    async def mock_query_selector(_: object, key: str) -> object | None:
        nonlocal call_count
        call_count += 1
        if call_count <= 3 and key == "popup_dismiss_today":
            return element
        return None

    adapter._query_selector = mock_query_selector  # type: ignore[method-assign]

    dismissed = await adapter.dismiss_popups()

    assert dismissed == 1
    element.click.assert_awaited_once()
    page.wait_for_timeout.assert_awaited_once_with(800)


@pytest.mark.asyncio
async def test_dismiss_popups_skips_invisible() -> None:
    adapter, _ = _make_adapter()
    element = MagicMock()
    element.is_visible = AsyncMock(return_value=False)
    element.click = AsyncMock()

    async def mock_query_selector(_: object, key: str) -> object | None:
        del key
        return element

    adapter._query_selector = mock_query_selector  # type: ignore[method-assign]

    dismissed = await adapter.dismiss_popups(max_rounds=1)

    assert dismissed == 0
    element.click.assert_not_awaited()


@pytest.mark.asyncio
async def test_dismiss_popups_no_popups() -> None:
    adapter, page = _make_adapter()

    async def mock_query_selector(_: object, key: str) -> object | None:
        del key
        return None

    adapter._query_selector = mock_query_selector  # type: ignore[method-assign]

    dismissed = await adapter.dismiss_popups()

    assert dismissed == 0
    page.wait_for_timeout.assert_not_awaited()


@pytest.mark.asyncio
async def test_navigate_to_chat_dismisses_popups_after_session_list() -> None:
    adapter, page = _make_adapter("about:blank")
    call_order: list[str] = []

    async def goto(url: str, wait_until: str, timeout: int) -> None:
        assert wait_until == "domcontentloaded"
        assert timeout == 30000
        page.url = url

    async def dismiss_popups(max_rounds: int = 3) -> int:
        assert max_rounds == 3
        call_order.append("dismiss")
        return 1

    async def find_chat_frame() -> object:
        call_order.append("find")
        return page

    page.goto = AsyncMock(side_effect=goto)
    adapter._wait_for_selector = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    adapter.dismiss_popups = dismiss_popups  # type: ignore[method-assign]
    adapter._find_chat_frame = AsyncMock(side_effect=find_chat_frame)  # type: ignore[method-assign]

    await adapter.navigate_to_chat()

    assert page.goto.await_args_list[0].args[0] == PDD_CHAT_URL
    assert call_order == ["dismiss", "find"]


@pytest.mark.asyncio
async def test_shop_loop_periodically_dismisses_popups(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_scheduler = scheduler.ShopScheduler()
    dismiss_started = asyncio.Event()

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            del shop_id, proxy
            return object()

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        def __init__(self) -> None:
            self.dismiss_calls: list[int] = []

        async def dismiss_popups(self, max_rounds: int = 3) -> int:
            self.dismiss_calls.append(max_rounds)
            dismiss_started.set()
            await asyncio.sleep(60)
            return 1

        async def get_session_list(self) -> list[object]:
            return []

    fake_engine = FakeEngine()
    fake_adapter = FakeAdapter()

    async def no_sleep(seconds: float) -> None:
        del seconds
        return None

    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "")
    monkeypatch.setattr(scheduler, "_update_shop_status", lambda shop_id, **kwargs: None)
    monkeypatch.setattr(scheduler, "_load_runtime_configuration", lambda shop_id: ({}, object()))
    monkeypatch.setattr(scheduler, "_save_shop_cookies", AsyncMock())
    monkeypatch.setattr(scheduler, "_sleep", no_sleep)
    monkeypatch.setattr(scheduler, "DEFAULT_LOGIN_CHECK_INTERVAL", 9999)
    monkeypatch.setattr(scheduler, "DEFAULT_COOKIE_SAVE_INTERVAL", 999999.0)
    monkeypatch.setattr(scheduler, "DEFAULT_MEMORY_CLEANUP_INTERVAL", 999999.0)
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: fake_adapter)
    monkeypatch.setattr(shop_scheduler, "_navigate_adapter_to_chat", AsyncMock(return_value=False))
    monkeypatch.setattr(shop_scheduler, "_is_adapter_logged_in", AsyncMock(return_value=True))

    task = asyncio.create_task(shop_scheduler._shop_loop("shop-1"))
    await asyncio.wait_for(dismiss_started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert fake_adapter.dismiss_calls == [1]
    assert fake_engine.closed_shops == ["shop-1"]
