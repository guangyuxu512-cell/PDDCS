from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.response import ok
from backend.services.dashboard_service import get_summary


router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
@router.get("/dashboard/summary")
async def api_dashboard() -> dict[str, Any]:
    summary = get_summary()
    return ok(summary.model_dump())
