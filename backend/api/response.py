"""统一响应包装，匹配前端 ApiResponse<T> 结构。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    code: int = 0
    msg: str = "ok"
    data: Any = None


def ok(data: Any = None) -> dict[str, Any]:
    """成功响应。"""
    return {"code": 0, "msg": "ok", "data": data}


def fail(msg: str, code: int = -1) -> dict[str, Any]:
    """失败响应。"""
    return {"code": code, "msg": msg, "data": None}
