from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from backend.api.response import fail, ok
from backend.services.chat_service import list_sessions, takeover_session


router = APIRouter(tags=["chat"])


@router.get("/chat/sessions")
async def api_list_sessions() -> dict[str, Any]:
    sessions = list_sessions()
    return ok([session.model_dump() for session in sessions])


@router.post("/chat/sessions/{session_id}/takeover")
async def api_takeover(session_id: str) -> dict[str, Any]:
    session = takeover_session(session_id)
    if session is None:
        return fail("会话不存在")
    return ok(session.model_dump())
