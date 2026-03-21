from __future__ import annotations

import pytest

from backend.services import scheduler


class FakeWorkerManager:
    def __init__(self) -> None:
        self.assigned: list[str] = []
        self.removed: list[str] = []

    def assign_shop(self, shop_id: str) -> bool:
        self.assigned.append(shop_id)
        return True

    def remove_shop(self, shop_id: str) -> bool:
        self.removed.append(shop_id)
        return True

    def get_running_shops(self) -> list[str]:
        return ["shop-1"]


@pytest.mark.asyncio
async def test_scheduler_module_delegates_to_worker_manager_when_configured() -> None:
    manager = FakeWorkerManager()
    scheduler.configure_worker_manager(manager)

    try:
        assert await scheduler.start_shop("shop-1") is True
        assert await scheduler.stop_shop("shop-1") is True
        assert scheduler.get_running_shops() == ["shop-1"]
        assert manager.assigned == ["shop-1"]
        assert manager.removed == ["shop-1"]
    finally:
        scheduler.configure_worker_manager(None)
