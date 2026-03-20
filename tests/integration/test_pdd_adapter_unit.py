"""PDD 适配器单元测试，仅测试数据结构和辅助逻辑。"""

from __future__ import annotations

import hashlib

import pytest

from backend.adapters.base import RawMessage, SessionInfo
from backend.adapters.pdd import PDD_CHAT_URL, SELECTORS
from backend.adapters.selector_config import SelectorConfig
from backend.engines.playwright_engine import PlaywrightEngine


def test_raw_message_fields() -> None:
    message = RawMessage(
        session_id="buyer1",
        buyer_id="buyer1",
        buyer_name="张三",
        content="你好",
        sender="buyer",
        timestamp="2026-03-19T06:00:00",
        dedup_key="shop1:buyer1:0:abc123",
    )
    assert message.sender == "buyer"
    assert message.dedup_key.startswith("shop1:")


def test_session_info_fields() -> None:
    info = SessionInfo(
        session_id="buyer1",
        buyer_id="buyer1",
        buyer_name="张三",
        last_message="你好",
        unread=True,
    )
    assert info.unread is True


def test_selectors_not_empty() -> None:
    for key, value in SELECTORS.items():
        assert isinstance(value, SelectorConfig), f"Selector '{key}' is not wrapped by SelectorConfig"
        assert value.primary, f"Selector '{key}' primary selector is empty"
        assert all(selector for selector in value.all()), f"Selector '{key}' contains empty fallback values"


def test_chat_url() -> None:
    assert "pinduoduo.com/chat" in PDD_CHAT_URL


def test_dedup_key_generation() -> None:
    content = "你好，我要退款"
    content_hash = hashlib.md5(content.encode("utf-8")).hexdigest()[:8]
    dedup_key = f"shop1:buyer1:0:{content_hash}"
    assert content_hash in dedup_key
    assert len(dedup_key) > 0


def test_playwright_engine_default_state() -> None:
    engine = PlaywrightEngine()
    assert engine.is_running is False


@pytest.mark.asyncio
async def test_playwright_engine_requires_start_before_creating_context() -> None:
    engine = PlaywrightEngine()
    with pytest.raises(RuntimeError):
        await engine.get_or_create_context("shop-1")
