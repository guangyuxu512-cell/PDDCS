from __future__ import annotations

import logging
from pathlib import Path

import pytest

from backend.engines.cookie_manager import CookieManager


class FakeNonNavigatingPage:
    def __init__(
        self,
        *,
        url: str,
        element: object | None = object(),
        query_raises: bool = False,
    ) -> None:
        self.url = url
        self.element = element
        self.query_raises = query_raises
        self.goto_called = False
        self.selectors: list[str] = []

    async def goto(self, *args: object, **kwargs: object) -> None:
        del args, kwargs
        self.goto_called = True
        raise AssertionError("goto should not be called")

    async def query_selector(self, selector: str) -> object | None:
        self.selectors.append(selector)
        if self.query_raises:
            raise RuntimeError("query failed")
        return self.element


@pytest.mark.asyncio
async def test_is_valid_without_navigate_checks_dom_without_calling_goto(tmp_path: Path) -> None:
    manager = CookieManager(data_dir=str(tmp_path))
    valid_page = FakeNonNavigatingPage(url="https://mms.pinduoduo.com/chat-merchant/#/")
    login_page = FakeNonNavigatingPage(url="https://mms.pinduoduo.com/login")
    broken_page = FakeNonNavigatingPage(
        url="https://mms.pinduoduo.com/chat-merchant/#/",
        query_raises=True,
    )

    assert await manager.is_valid_without_navigate(valid_page) is True
    assert await manager.is_valid_without_navigate(login_page) is False
    assert await manager.is_valid_without_navigate(broken_page) is False
    assert valid_page.goto_called is False
    assert login_page.goto_called is False
    assert broken_page.goto_called is False
    assert valid_page.selectors == ["li.chat-item"]
    assert login_page.selectors == []
    assert broken_page.selectors == ["li.chat-item"]


@pytest.mark.asyncio
async def test_periodic_save_logs_and_swallows_save_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    manager = CookieManager(data_dir=str(tmp_path))

    async def failing_save(shop_id: str, context: object) -> None:
        del shop_id, context
        raise RuntimeError("save failed")

    monkeypatch.setattr(manager, "save", failing_save)

    with caplog.at_level(logging.ERROR):
        await manager.periodic_save("shop-1", object())

    assert "Failed periodic cookie save for shop shop-1" in caplog.text
