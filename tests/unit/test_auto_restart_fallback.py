from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.scheduler import ShopScheduler


def test_on_task_done_schedules_delayed_restart_for_non_cancelled_crash() -> None:
    shop_scheduler = ShopScheduler()
    task = MagicMock(spec=asyncio.Task)
    task.result.side_effect = RuntimeError("boom")
    shop_scheduler._running_tasks["shop-1"] = task
    loop = MagicMock()

    with (
        patch("backend.services.scheduler._get_shop_restart_policy", return_value=True),
        patch("backend.services.scheduler._update_shop_status") as mock_update_status,
        patch("backend.services.scheduler.asyncio.get_event_loop", return_value=loop),
    ):
        shop_scheduler._on_task_done("shop-1", task)

    mock_update_status.assert_called_once_with("shop-1", is_online=False)
    loop.call_later.assert_called_once()
    delay, callback = loop.call_later.call_args.args
    assert delay == 10.0
    assert callable(callback)
    assert "shop-1" not in shop_scheduler._running_tasks


def test_on_task_done_does_not_schedule_restart_when_policy_disabled() -> None:
    shop_scheduler = ShopScheduler()
    task = MagicMock(spec=asyncio.Task)
    task.result.side_effect = RuntimeError("boom")
    loop = MagicMock()

    with (
        patch("backend.services.scheduler._get_shop_restart_policy", return_value=False),
        patch("backend.services.scheduler._update_shop_status") as mock_update_status,
        patch("backend.services.scheduler.asyncio.get_event_loop", return_value=loop),
    ):
        shop_scheduler._on_task_done("shop-1", task)

    mock_update_status.assert_called_once_with("shop-1", is_online=False)
    loop.call_later.assert_not_called()


@pytest.mark.asyncio
async def test_auto_restart_shop_skips_when_task_is_already_running() -> None:
    shop_scheduler = ShopScheduler()
    running_task = MagicMock(spec=asyncio.Task)
    running_task.done.return_value = False
    shop_scheduler._running_tasks["shop-1"] = running_task

    with (
        patch("backend.services.scheduler._get_shop_restart_policy", return_value=True),
        patch.object(shop_scheduler, "start_shop", new_callable=AsyncMock) as mock_start_shop,
    ):
        await shop_scheduler._auto_restart_shop("shop-1")

    mock_start_shop.assert_not_awaited()


@pytest.mark.asyncio
async def test_auto_restart_shop_skips_when_policy_is_disabled() -> None:
    shop_scheduler = ShopScheduler()

    with (
        patch("backend.services.scheduler._get_shop_restart_policy", return_value=False),
        patch.object(shop_scheduler, "start_shop", new_callable=AsyncMock) as mock_start_shop,
    ):
        await shop_scheduler._auto_restart_shop("shop-1")

    mock_start_shop.assert_not_awaited()
