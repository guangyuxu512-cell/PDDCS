from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from backend.engines import playwright_engine as playwright_engine_module
from backend.engines.playwright_engine import PlaywrightEngine
from backend.engines.profile_factory import ProfileFactory


class FakePage:
    def __init__(self, url: str = "about:blank", closed: bool = False, close_raises: bool = False) -> None:
        self.url = url
        self._closed = closed
        self._close_raises = close_raises
        self.close_calls = 0

    def is_closed(self) -> bool:
        return self._closed

    async def close(self) -> None:
        self.close_calls += 1
        if self._close_raises:
            raise RuntimeError("page close failed")
        self._closed = True


class FakeContext:
    def __init__(
        self,
        pages: list[FakePage] | None = None,
        *,
        close_raises: bool = False,
        pages_raise: bool = False,
    ) -> None:
        self._pages = pages or []
        self._close_raises = close_raises
        self._pages_raise = pages_raise
        self.closed = False
        self._listeners: dict[str, object] = {}

    @property
    def pages(self) -> list[FakePage]:
        if self._pages_raise:
            raise RuntimeError("context dead")
        return self._pages

    def on(self, event: str, callback: object) -> None:
        self._listeners[event] = callback

    async def new_page(self) -> FakePage:
        page = FakePage(url="about:blank")
        self._pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True
        if self._close_raises:
            raise RuntimeError("context close failed")
        callback = self._listeners.get("close")
        if callback is not None:
            callback()


class FakeCookieManager:
    def __init__(self, *, save_raises: bool = False) -> None:
        self.loaded: list[tuple[str, FakeContext]] = []
        self.saved: list[tuple[str, FakeContext]] = []
        self._save_raises = save_raises

    async def load(self, shop_id: str, context: FakeContext) -> bool:
        self.loaded.append((shop_id, context))
        return True

    async def save(self, shop_id: str, context: FakeContext) -> None:
        self.saved.append((shop_id, context))
        if self._save_raises:
            raise RuntimeError("save failed")


class QueueChromium:
    def __init__(self, contexts: list[FakeContext], *, delay_seconds: float = 0.0) -> None:
        self._contexts = contexts
        self._delay_seconds = delay_seconds
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.active_launches = 0
        self.max_active_launches = 0

    async def launch_persistent_context(self, user_data_dir: str, **kwargs: object) -> FakeContext:
        self.calls.append((user_data_dir, kwargs))
        self.active_launches += 1
        self.max_active_launches = max(self.max_active_launches, self.active_launches)
        try:
            if self._delay_seconds > 0:
                await asyncio.sleep(self._delay_seconds)
            return self._contexts.pop(0)
        finally:
            self.active_launches -= 1


class FakePlaywright:
    def __init__(self, chromium: QueueChromium) -> None:
        self.chromium = chromium
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


@pytest.mark.asyncio
async def test_open_shop_concurrent_calls_share_one_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = QueueChromium([FakeContext()], delay_seconds=0.05)
    engine = PlaywrightEngine()
    engine._playwright = FakePlaywright(chromium)
    engine._profile_factory = ProfileFactory(base_dir=str(tmp_path / "profiles"))
    engine._cookie_manager = FakeCookieManager()

    monkeypatch.setattr(playwright_engine_module, "MAX_CONCURRENT_SHOPS", 1)
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.delenv("CHROME_EXECUTABLE_PATH", raising=False)

    first_page, second_page = await asyncio.gather(
        engine.open_shop("shop-1"),
        engine.open_shop("shop-1"),
    )

    assert first_page is second_page
    assert len(chromium.calls) == 1
    assert chromium.max_active_launches == 1
    assert "shop-1" in engine._shop_start_times


@pytest.mark.asyncio
async def test_cleanup_memory_info_and_liveness_cover_normal_and_dead_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = PlaywrightEngine()
    keep_page = FakePage(url="https://mms.pinduoduo.com/chat-merchant/#/")
    extra_page = FakePage(url="https://mms.pinduoduo.com/other")
    blank_page = FakePage(url="about:blank")
    context = FakeContext(pages=[blank_page, keep_page, extra_page, FakePage(closed=True)])
    engine._contexts["shop-1"] = context
    engine._contexts["dead-shop"] = FakeContext(pages_raise=True)
    now = asyncio.get_running_loop().time()
    engine._shop_start_times["shop-1"] = now - 12.5

    class FakeMemoryInfo:
        rss = 64 * 1024 * 1024

    class FakeProcess:
        def memory_info(self) -> FakeMemoryInfo:
            return FakeMemoryInfo()

    class FakeVirtualMemory:
        percent = 48.2

    monkeypatch.setattr(playwright_engine_module.psutil, "Process", lambda: FakeProcess())
    monkeypatch.setattr(playwright_engine_module.psutil, "virtual_memory", lambda: FakeVirtualMemory())

    closed = await engine.cleanup_extra_pages("shop-1")
    memory_info = await engine.get_memory_info()

    assert closed == 2
    assert blank_page.is_closed() is True
    assert extra_page.is_closed() is True
    assert keep_page.is_closed() is False
    assert await engine.is_context_alive("shop-1") is True
    assert await engine.is_context_alive("dead-shop") is False
    assert await engine.is_context_alive("missing-shop") is False
    assert memory_info["active_shops"] == 2
    assert memory_info["shop_details"]["shop-1"]["pages"] == 1
    assert memory_info["shop_details"]["shop-1"]["uptime_seconds"] >= 12.0
    assert memory_info["rss_mb"] == 64.0
    assert memory_info["system_memory_percent"] == 48.2


@pytest.mark.asyncio
async def test_restart_shop_reopens_after_close_and_close_shop_swallows_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    old_context = FakeContext(pages=[FakePage(url="https://mms.pinduoduo.com/chat-merchant/#/")], close_raises=True)
    new_context = FakeContext()
    chromium = QueueChromium([new_context])
    cookie_manager = FakeCookieManager(save_raises=True)

    engine = PlaywrightEngine()
    engine._playwright = FakePlaywright(chromium)
    engine._profile_factory = ProfileFactory(base_dir=str(tmp_path / "profiles"))
    engine._cookie_manager = cookie_manager
    engine._contexts["shop-1"] = old_context
    engine._shop_start_times["shop-1"] = asyncio.get_running_loop().time() - 3.0

    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(playwright_engine_module.asyncio, "sleep", fake_sleep)
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.delenv("CHROME_EXECUTABLE_PATH", raising=False)

    restarted_page = await engine.restart_shop("shop-1", proxy="http://127.0.0.1:7890")

    assert old_context.closed is True
    assert cookie_manager.saved == [("shop-1", old_context)]
    assert sleep_calls == [5.0]
    assert restarted_page is new_context.pages[0]
    assert engine._contexts["shop-1"] is new_context
    assert len(chromium.calls) == 1
    assert chromium.calls[0][1]["proxy"] == {"server": "http://127.0.0.1:7890"}
