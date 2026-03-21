from __future__ import annotations

import asyncio
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.adapters import RawMessage, SessionInfo
from backend.db import database
from backend.services import scheduler


def _cleanup_database_files(db_path: Path) -> None:
    for path in (db_path, Path(f"{db_path}-shm"), Path(f"{db_path}-wal")):
        path.unlink(missing_ok=True)


def _insert_shop(shop_id: str, *, is_online: int = 1, ai_enabled: int = 1) -> None:
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO shops (id, name, platform, username, password, is_online, ai_enabled) VALUES (?,?,?,?,?,?,?)",
            (shop_id, f"店铺-{shop_id}", "pdd", "seller", "secret", is_online, ai_enabled),
        )
        conn.execute("INSERT INTO shop_configs (shop_id) VALUES (?)", (shop_id,))


@pytest.fixture()
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    db_dir = tmp_path / "data"
    db_path = db_dir / "scheduler-resilience.db"
    monkeypatch.setattr(database, "DB_DIR", db_dir)
    monkeypatch.setattr(database, "DB_PATH", db_path)
    _cleanup_database_files(db_path)
    database.init_database()
    _insert_shop("shop-1")
    yield db_path
    _cleanup_database_files(db_path)


def test_update_shop_status_updates_allowed_fields(isolated_database: Path) -> None:
    del isolated_database

    scheduler._update_shop_status(
        "shop-1",
        is_online=True,
        cookie_valid=True,
        last_active_at="2026-03-21T12:00:00",
        today_served_count=8,
        ignored_field="value",
    )

    with database.get_db() as conn:
        row = conn.execute(
            "SELECT is_online, cookie_valid, last_active_at, today_served_count, updated_at FROM shops WHERE id=?",
            ("shop-1",),
        ).fetchone()

    assert row is not None
    assert row["is_online"] == 1
    assert row["cookie_valid"] == 1
    assert row["last_active_at"] == "2026-03-21T12:00:00"
    assert row["today_served_count"] == 8
    assert row["updated_at"] != ""


@pytest.mark.asyncio
async def test_process_session_sends_reply_message(monkeypatch: pytest.MonkeyPatch) -> None:
    shop_scheduler = scheduler.ShopScheduler()
    session_info = SessionInfo(session_id="session-1", buyer_id="buyer-1", buyer_name="买家A")
    buyer_message = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="什么时候发货？",
        sender="buyer",
        timestamp="2026-03-21T12:00:00",
        dedup_key="dedup-1",
    )

    class FakeAdapter:
        def __init__(self) -> None:
            self.switched_sessions: list[str] = []
            self.sent_messages: list[tuple[str, str]] = []

        async def switch_to_session(self, session_id: str) -> None:
            self.switched_sessions.append(session_id)

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            assert session_id == "session-1"
            return [buyer_message]

        async def send_message(self, session_id: str, text: str) -> bool:
            self.sent_messages.append((session_id, text))
            return True

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            raise AssertionError("trigger_escalation should not be called in reply path")

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

    assert fake_adapter.switched_sessions == ["session-1"]
    assert fake_adapter.sent_messages == [("session-1", "今天发货")]


@pytest.mark.asyncio
async def test_process_session_triggers_escalation_with_fallback(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    session_info = SessionInfo(session_id="session-1", buyer_id="buyer-1", buyer_name="买家A")
    buyer_message = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="我要投诉",
        sender="buyer",
        timestamp="2026-03-21T12:00:00",
        dedup_key="dedup-2",
    )

    class FakeAdapter:
        def __init__(self) -> None:
            self.sent_messages: list[tuple[str, str]] = []
            self.escalations: list[tuple[str, str]] = []

        async def switch_to_session(self, session_id: str) -> None:
            assert session_id == "session-1"

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            assert session_id == "session-1"
            return [buyer_message]

        async def send_message(self, session_id: str, text: str) -> bool:
            self.sent_messages.append((session_id, text))
            return True

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            self.escalations.append((session_id, target_agent))
            return True

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
        return SimpleNamespace(action="escalate", session_id="session-1")

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "process_buyer_message", fake_process_buyer_message)

    await shop_scheduler._process_session(
        "shop-1",
        fake_adapter,
        session_info,
        {"ai_enabled": True, "escalation_fallback_msg": "为您转人工处理", "human_agent_name": "客服A"},
        object(),
    )

    assert fake_adapter.sent_messages == [("session-1", "为您转人工处理")]
    assert fake_adapter.escalations == [("session-1", "客服A")]


@pytest.mark.asyncio
async def test_process_session_stores_message_without_reply_when_ai_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop_scheduler = scheduler.ShopScheduler()
    session_info = SessionInfo(session_id="session-1", buyer_id="buyer-1", buyer_name="买家A")
    buyer_message = RawMessage(
        session_id="session-1",
        buyer_id="buyer-1",
        buyer_name="买家A",
        content="只入库不回复",
        sender="buyer",
        timestamp="2026-03-21T12:00:00",
        dedup_key="dedup-store-only",
    )

    class FakeAdapter:
        def __init__(self) -> None:
            self.sent_messages: list[tuple[str, str]] = []

        async def switch_to_session(self, session_id: str) -> None:
            assert session_id == "session-1"

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            assert session_id == "session-1"
            return [buyer_message]

        async def send_message(self, session_id: str, text: str) -> bool:
            self.sent_messages.append((session_id, text))
            return True

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            raise AssertionError("trigger_escalation should not be called when AI is disabled")

    async def fake_process_buyer_message(
        shop_id: str,
        raw_msg: RawMessage,
        llm_client: object,
        ai_enabled: bool = True,
    ) -> SimpleNamespace:
        assert shop_id == "shop-1"
        assert raw_msg is buyer_message
        assert llm_client is not None
        assert ai_enabled is False
        return SimpleNamespace(action="stored", session_id="session-1")

    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "process_buyer_message", fake_process_buyer_message)

    await shop_scheduler._process_session(
        "shop-1",
        fake_adapter,
        session_info,
        {"ai_enabled": False},
        object(),
    )

    assert fake_adapter.sent_messages == []


@pytest.mark.asyncio
async def test_shop_loop_handles_relogin_cookie_save_and_cleanup(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()
    first_poll_started = asyncio.Event()
    context = object()

    class FakeCookieManager:
        def __init__(self) -> None:
            self.saved: list[tuple[str, object]] = []

        async def save(self, shop_id: str, current_context: object) -> None:
            self.saved.append((shop_id, current_context))

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self._contexts: dict[str, object] = {}
            self._cookie_manager = FakeCookieManager()
            self.open_calls: list[tuple[str, str]] = []
            self.cleanup_calls: list[str] = []
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            self.open_calls.append((shop_id, proxy))
            self._contexts[shop_id] = context
            return object()

        async def cleanup_extra_pages(self, shop_id: str) -> int:
            self.cleanup_calls.append(shop_id)
            return 1

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class FakeAdapter:
        def __init__(self) -> None:
            self.navigate_calls = 0
            self.login_results = [False, False, False]
            self.wait_calls: list[int] = []

        async def navigate_to_chat(self) -> None:
            self.navigate_calls += 1

        async def is_logged_in(self) -> bool:
            return self.login_results.pop(0)

        async def wait_for_login(self, timeout_ms: int = 120000) -> bool:
            self.wait_calls.append(timeout_ms)
            return True

        async def get_session_list(self) -> list[SessionInfo]:
            first_poll_started.set()
            await asyncio.sleep(60)
            return []

        async def switch_to_session(self, session_id: str) -> None:
            raise AssertionError("switch_to_session should not be called in this test")

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            raise AssertionError("fetch_messages should not be called in this test")

        async def send_message(self, session_id: str, text: str) -> bool:
            raise AssertionError("send_message should not be called in this test")

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            raise AssertionError("trigger_escalation should not be called in this test")

    fake_engine = FakeEngine()
    fake_adapter = FakeAdapter()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "http://127.0.0.1:7890")
    monkeypatch.setattr(scheduler, "_load_runtime_configuration", lambda shop_id: ({}, object()))
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: fake_adapter)
    monkeypatch.setattr(scheduler, "DEFAULT_LOGIN_CHECK_INTERVAL", 1)
    monkeypatch.setattr(scheduler, "DEFAULT_COOKIE_SAVE_INTERVAL", 0.0)
    monkeypatch.setattr(scheduler, "DEFAULT_MEMORY_CLEANUP_INTERVAL", 0.0)

    task = asyncio.create_task(shop_scheduler._shop_loop("shop-1"))
    await asyncio.wait_for(first_poll_started.wait(), timeout=1.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 1
    assert row["cookie_valid"] == 1
    assert fake_engine.open_calls == [("shop-1", "http://127.0.0.1:7890")]
    assert fake_engine.cleanup_calls == ["shop-1"]
    assert fake_engine.closed_shops == ["shop-1"]
    assert fake_adapter.navigate_calls == 2
    assert fake_adapter.wait_calls == [120000, 120000]
    assert fake_engine._cookie_manager.saved == [("shop-1", context), ("shop-1", context), ("shop-1", context)]


@pytest.mark.asyncio
async def test_shop_loop_marks_shop_offline_after_crash_retries(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    shop_scheduler = scheduler.ShopScheduler()

    class FakeEngine:
        def __init__(self) -> None:
            self.is_running = False
            self.open_calls: list[tuple[str, str]] = []
            self.restart_calls: list[tuple[str, str]] = []
            self.closed_shops: list[str] = []

        async def start(self) -> None:
            self.is_running = True

        async def open_shop(self, shop_id: str, proxy: str = "") -> object:
            self.open_calls.append((shop_id, proxy))
            return object()

        async def restart_shop(self, shop_id: str, proxy: str = "") -> object:
            self.restart_calls.append((shop_id, proxy))
            return object()

        async def close_shop(self, shop_id: str) -> None:
            self.closed_shops.append(shop_id)

    class CrashAdapter:
        async def navigate_to_chat(self) -> None:
            raise RuntimeError("boom")

        async def get_session_list(self) -> list[SessionInfo]:
            return []

        async def switch_to_session(self, session_id: str) -> None:
            raise AssertionError("switch_to_session should not be reached")

        async def fetch_messages(self, session_id: str) -> list[RawMessage]:
            raise AssertionError("fetch_messages should not be reached")

        async def send_message(self, session_id: str, text: str) -> bool:
            raise AssertionError("send_message should not be reached")

        async def trigger_escalation(self, session_id: str, target_agent: str) -> bool:
            raise AssertionError("trigger_escalation should not be reached")

    async def no_sleep(seconds: float) -> None:
        del seconds
        return None

    fake_engine = FakeEngine()
    monkeypatch.setattr(scheduler, "engine", fake_engine)
    monkeypatch.setattr(scheduler, "_sleep", no_sleep)
    monkeypatch.setattr(scheduler, "_get_shop_platform", lambda shop_id: "pdd")
    monkeypatch.setattr(scheduler, "_get_shop_proxy", lambda shop_id: "http://127.0.0.1:7890")
    monkeypatch.setattr(scheduler, "DEFAULT_CRASH_RECOVERY_MAX_RETRIES", 1)
    monkeypatch.setattr(shop_scheduler, "_create_adapter", lambda platform, page, shop_id: CrashAdapter())

    await shop_scheduler._shop_loop("shop-1")

    with database.get_db() as conn:
        row = conn.execute("SELECT is_online, cookie_valid FROM shops WHERE id=?", ("shop-1",)).fetchone()

    assert row is not None
    assert row["is_online"] == 0
    assert row["cookie_valid"] == 0
    assert fake_engine.open_calls == [
        ("shop-1", "http://127.0.0.1:7890"),
        ("shop-1", "http://127.0.0.1:7890"),
    ]
    assert fake_engine.restart_calls == [("shop-1", "http://127.0.0.1:7890")]
    assert fake_engine.closed_shops == ["shop-1"]


@pytest.mark.asyncio
async def test_start_all_online_shops_starts_shops_concurrently(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    _insert_shop("shop-2")
    shop_scheduler = scheduler.ShopScheduler()
    both_started = asyncio.Event()
    release = asyncio.Event()
    started_shop_ids: list[str] = []

    async def fake_start_shop(shop_id: str) -> bool:
        started_shop_ids.append(shop_id)
        if len(started_shop_ids) == 2:
            both_started.set()
        await release.wait()
        return shop_id == "shop-1"

    monkeypatch.setattr(shop_scheduler, "start_shop", fake_start_shop)

    task = asyncio.create_task(shop_scheduler.start_all_online_shops())
    await asyncio.wait_for(both_started.wait(), timeout=1.0)
    release.set()
    count = await asyncio.wait_for(task, timeout=1.0)

    assert set(started_shop_ids) == {"shop-1", "shop-2"}
    assert count == 1


@pytest.mark.asyncio
async def test_start_all_online_shops_includes_ai_disabled_shop(
    isolated_database: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del isolated_database
    _insert_shop("shop-2", ai_enabled=0)
    shop_scheduler = scheduler.ShopScheduler()
    started_shop_ids: list[str] = []

    async def fake_start_shop(shop_id: str) -> bool:
        started_shop_ids.append(shop_id)
        return True

    monkeypatch.setattr(shop_scheduler, "start_shop", fake_start_shop)

    count = await shop_scheduler.start_all_online_shops()

    assert set(started_shop_ids) == {"shop-1", "shop-2"}
    assert count == 2
