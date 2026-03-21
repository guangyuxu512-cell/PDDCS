from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.db import database
from backend.engines import human_simulator as human_simulator_module
from backend.engines.cookie_manager import CookieManager
from backend.engines.human_simulator import HumanSimulator
from backend.engines.playwright_engine import PlaywrightEngine
from backend.engines.profile_factory import ProfileFactory


class FakeCookieContext:
    def __init__(self, cookies: list[dict[str, str]] | None = None) -> None:
        self._cookies = cookies or [{"name": "sid", "value": "cookie"}]
        self.loaded_cookies: list[dict[str, str]] | None = None

    async def cookies(self) -> list[dict[str, str]]:
        return self._cookies

    async def add_cookies(self, cookies: list[dict[str, str]]) -> None:
        self.loaded_cookies = cookies


class FakeGotoPage:
    def __init__(self, final_url: str = "https://mms.pinduoduo.com/chat-merchant/#/", should_raise: bool = False) -> None:
        self.url = ""
        self._final_url = final_url
        self._should_raise = should_raise

    async def goto(self, url: str, wait_until: str, timeout: int) -> None:
        del wait_until, timeout
        if self._should_raise:
            raise RuntimeError("goto failed")
        self.url = url if self._final_url == "" else self._final_url


class FakeMouse:
    def __init__(self) -> None:
        self.events: list[tuple[object, ...]] = []

    async def move(self, x: float, y: float, steps: int = 1) -> None:
        self.events.append(("move", round(x, 2), round(y, 2), steps))

    async def down(self) -> None:
        self.events.append(("down",))

    async def up(self) -> None:
        self.events.append(("up",))

    async def wheel(self, delta_x: int, delta_y: int) -> None:
        self.events.append(("wheel", delta_x, delta_y))


class FakeInteractionTarget:
    def __init__(self, fail_fill: bool = False) -> None:
        self.calls: list[tuple[str, object]] = []
        self._fail_fill = fail_fill

    async def click(self, timeout: int = 5000) -> None:
        self.calls.append(("click", timeout))

    async def fill(self, value: str) -> None:
        self.calls.append(("fill", value))
        if self._fail_fill:
            raise RuntimeError("fill failed")

    async def press(self, key: str) -> None:
        self.calls.append(("press", key))

    async def type(self, text: str, delay: int = 0) -> None:
        del delay
        self.calls.append(("type", text))

    async def scroll_into_view_if_needed(self, timeout: int = 5000) -> None:
        self.calls.append(("scroll_into_view_if_needed", timeout))

    async def bounding_box(self) -> dict[str, float]:
        return {"x": 100.0, "y": 120.0, "width": 50.0, "height": 20.0}


class FakeLocatorWrapper:
    def __init__(self, target: FakeInteractionTarget) -> None:
        self.first = target


class FakeHumanPage:
    def __init__(self, target: FakeInteractionTarget) -> None:
        self._target = target
        self.mouse = FakeMouse()

    def locator(self, selector: str) -> FakeLocatorWrapper:
        assert selector == "textarea"
        return FakeLocatorWrapper(self._target)


class FakePageHandle:
    def __init__(self) -> None:
        self._closed = False

    def is_closed(self) -> bool:
        return self._closed


class FakePersistentContext:
    def __init__(self) -> None:
        self.pages: list[FakePageHandle] = []
        self.closed = False
        self._listeners: dict[str, object] = {}

    def on(self, event: str, callback: object) -> None:
        self._listeners[event] = callback

    async def new_page(self) -> FakePageHandle:
        page = FakePageHandle()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        self.closed = True
        callback = self._listeners.get("close")
        if callback is not None:
            callback()


class FakeChromium:
    def __init__(self, context: FakePersistentContext) -> None:
        self._context = context
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def launch_persistent_context(self, user_data_dir: str, **kwargs: object) -> FakePersistentContext:
        self.calls.append((user_data_dir, kwargs))
        return self._context


class FakePlaywright:
    def __init__(self, context: FakePersistentContext) -> None:
        self.chromium = FakeChromium(context)
        self.stopped = False

    async def stop(self) -> None:
        self.stopped = True


class FakePlaywrightLauncher:
    def __init__(self, playwright: FakePlaywright) -> None:
        self._playwright = playwright

    async def start(self) -> FakePlaywright:
        return self._playwright


class FakeCookieManager:
    def __init__(self) -> None:
        self.loaded: list[tuple[str, FakePersistentContext]] = []
        self.saved: list[tuple[str, FakePersistentContext]] = []

    async def load(self, shop_id: str, context: FakePersistentContext) -> bool:
        self.loaded.append((shop_id, context))
        return True

    async def save(self, shop_id: str, context: FakePersistentContext) -> None:
        self.saved.append((shop_id, context))


def _prepare_cookie_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_dir = tmp_path / "data"
    db_path = db_dir / "cookies.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    database.init_database()
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password) VALUES (?,?,?,?,?)",
            ("shop-1", "测试店铺", "pdd", "seller", ""),
        )


def test_profile_factory_create_list_delete(tmp_path: Path) -> None:
    factory = ProfileFactory(base_dir=str(tmp_path / "profiles"))

    created_dir = Path(factory.get_or_create("shop-1"))

    assert created_dir.exists()
    assert factory.list_all() == ["shop-1"]
    assert factory.delete("shop-1") is True
    assert factory.delete("missing-shop") is False


@pytest.mark.asyncio
async def test_cookie_manager_save_and_load_roundtrip(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_cookie_database(tmp_path, monkeypatch)
    manager = CookieManager(data_dir=str(tmp_path))
    source_context = FakeCookieContext()
    target_context = FakeCookieContext(cookies=[])

    await manager.save("shop-1", source_context)
    with database.get_db() as conn:
        saved_row = conn.execute(
            "SELECT cookie_encrypted, cookie_fingerprint FROM shop_cookies WHERE shop_id=?",
            ("shop-1",),
        ).fetchone()

    loaded = await manager.load("shop-1", target_context)

    assert saved_row is not None
    assert saved_row["cookie_encrypted"] != json.dumps([{"name": "sid", "value": "cookie"}], ensure_ascii=False)
    assert saved_row["cookie_fingerprint"]
    assert loaded is True
    assert target_context.loaded_cookies == [{"name": "sid", "value": "cookie"}]


@pytest.mark.asyncio
async def test_cookie_manager_load_and_validate_cover_failure_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _prepare_cookie_database(tmp_path, monkeypatch)
    manager = CookieManager(data_dir=str(tmp_path))
    (tmp_path / "shop-1.json").write_text("{bad json", encoding="utf-8")

    invalid_payload_loaded = await manager.load("shop-1", FakeCookieContext())
    valid_cookie_state = await manager.is_valid(FakeGotoPage())
    invalid_cookie_state = await manager.is_valid(FakeGotoPage(final_url="https://mms.pinduoduo.com/login"))
    navigation_error_state = await manager.is_valid(FakeGotoPage(should_raise=True))

    assert invalid_payload_loaded is False
    assert valid_cookie_state is True
    assert invalid_cookie_state is False
    assert navigation_error_state is False


@pytest.mark.asyncio
async def test_human_simulator_typing_and_bezier_click(monkeypatch: pytest.MonkeyPatch) -> None:
    target = FakeInteractionTarget()
    page = FakeHumanPage(target)
    simulator = HumanSimulator(page)

    monkeypatch.setattr(human_simulator_module.random, "random", lambda: 1.0)
    monkeypatch.setattr(human_simulator_module.random, "uniform", lambda start, end: (start + end) / 2)

    await simulator.simulate_typing("textarea", "ok")
    await simulator.bezier_click(target)

    assert ("fill", "") in target.calls
    assert ("type", "o") in target.calls
    assert ("type", "k") in target.calls
    assert ("down",) in page.mouse.events
    assert ("up",) in page.mouse.events


@pytest.mark.asyncio
async def test_human_simulator_invalid_delay_range_raises() -> None:
    simulator = HumanSimulator(FakeHumanPage(FakeInteractionTarget()))

    with pytest.raises(ValueError):
        await simulator.random_delay(1.0, 0.5)


@pytest.mark.asyncio
async def test_playwright_engine_open_shop_uses_persistent_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_context = FakePersistentContext()
    fake_playwright = FakePlaywright(fake_context)
    fake_cookie_manager = FakeCookieManager()

    from backend.engines import playwright_engine as playwright_engine_module

    monkeypatch.setattr(
        playwright_engine_module,
        "async_playwright",
        lambda: FakePlaywrightLauncher(fake_playwright),
    )
    monkeypatch.delenv("CHROME_PATH", raising=False)
    monkeypatch.delenv("CHROME_EXECUTABLE_PATH", raising=False)

    engine = PlaywrightEngine()
    engine._profile_factory = ProfileFactory(base_dir=str(tmp_path / "profiles"))
    engine._cookie_manager = fake_cookie_manager

    await engine.start()
    page = await engine.open_shop("shop-1", proxy="http://127.0.0.1:7890")
    launch_path, launch_kwargs = fake_playwright.chromium.calls[0]

    assert page is fake_context.pages[0]
    assert launch_path.endswith("shop-1")
    assert launch_kwargs["channel"] == "chrome"
    assert launch_kwargs["proxy"] == {"server": "http://127.0.0.1:7890"}
    assert fake_cookie_manager.loaded == [("shop-1", fake_context)]

    await engine.close_shop("shop-1")
    await engine.stop()

    assert fake_cookie_manager.saved == [("shop-1", fake_context)]
    assert fake_context.closed is True
    assert fake_playwright.stopped is True


@pytest.mark.asyncio
async def test_playwright_engine_prefers_explicit_chrome_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_context = FakePersistentContext()
    fake_playwright = FakePlaywright(fake_context)
    fake_cookie_manager = FakeCookieManager()

    from backend.engines import playwright_engine as playwright_engine_module

    monkeypatch.setattr(
        playwright_engine_module,
        "async_playwright",
        lambda: FakePlaywrightLauncher(fake_playwright),
    )
    monkeypatch.setenv("CHROME_PATH", "C:/Chrome/chrome.exe")

    engine = PlaywrightEngine()
    engine._profile_factory = ProfileFactory(base_dir=str(tmp_path / "profiles"))
    engine._cookie_manager = fake_cookie_manager

    await engine.start()
    await engine.open_shop("shop-2")

    launch_kwargs = fake_playwright.chromium.calls[0][1]
    await engine.stop()

    assert launch_kwargs["executable_path"] == "C:/Chrome/chrome.exe"
    assert "channel" not in launch_kwargs
