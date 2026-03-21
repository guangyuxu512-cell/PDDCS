"""Webhook notification service."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from datetime import datetime
from typing import Any, Literal, TypeVar

import httpx

from backend.services.settings_service import get_settings


logger = logging.getLogger(__name__)

DEFAULT_NOTIFICATION_TIMEOUT_SECONDS = 10.0
DEFAULT_NOTIFICATION_RATE_LIMIT_SECONDS = 300.0
T = TypeVar("T")
NotificationLevel = Literal["info", "warning", "error"]
ResolvedWebhookType = Literal["feishu", "dingtalk", "wecom", "generic"]

_NOTIFICATION_RESERVATIONS: dict[str, float] = {}
_NOTIFICATION_LOCK = asyncio.Lock()


async def _wait(awaitable: Awaitable[T], timeout_seconds: float) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _normalize_webhook_type(value: str) -> ResolvedWebhookType:
    normalized = value.strip().lower()
    if normalized in {"feishu", "dingtalk", "wecom", "generic"}:
        return normalized  # type: ignore[return-value]
    return "feishu"


def _build_payload(
    title: str,
    content: str,
    level: NotificationLevel,
    webhook_type: ResolvedWebhookType,
) -> dict[str, Any]:
    if webhook_type == "feishu":
        return {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title,
                    }
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "plain_text",
                            "content": content,
                        },
                    }
                ],
            },
        }

    if webhook_type in {"dingtalk", "wecom"}:
        return {
            "msgtype": "text",
            "text": {
                "content": f"[{title}] {content}",
            },
        }

    return {
        "title": title,
        "content": content,
        "level": level,
        "timestamp": datetime.now().isoformat(),
    }


async def _reserve_event(event_key: str) -> float | None:
    now = time.monotonic()
    async with _NOTIFICATION_LOCK:
        last_sent = _NOTIFICATION_RESERVATIONS.get(event_key)
        if last_sent is not None and now - last_sent < DEFAULT_NOTIFICATION_RATE_LIMIT_SECONDS:
            return None
        _NOTIFICATION_RESERVATIONS[event_key] = now
        return now


async def _release_event(event_key: str, reserved_at: float) -> None:
    async with _NOTIFICATION_LOCK:
        if _NOTIFICATION_RESERVATIONS.get(event_key) == reserved_at:
            _NOTIFICATION_RESERVATIONS.pop(event_key, None)


async def send_notification(
    title: str,
    content: str,
    level: NotificationLevel = "warning",
    *,
    url: str | None = None,
    webhook_type: str | None = None,
    event_key: str | None = None,
    dedupe: bool = True,
) -> bool:
    settings = get_settings()
    resolved_url = str(url if url is not None else settings.notify_webhook_url).strip()
    if not resolved_url:
        return False

    resolved_type = _normalize_webhook_type(
        str(webhook_type if webhook_type is not None else settings.notify_webhook_type)
    )
    resolved_event_key = (event_key or f"{resolved_type}:{title}:{content}").strip()
    reserved_at: float | None = None

    if dedupe:
        reserved_at = await _reserve_event(resolved_event_key)
        if reserved_at is None:
            logger.debug("Skipped duplicate notification for event %s", resolved_event_key)
            return False

    payload = _build_payload(title=title, content=content, level=level, webhook_type=resolved_type)
    client = httpx.AsyncClient(timeout=DEFAULT_NOTIFICATION_TIMEOUT_SECONDS)
    try:
        response = await _wait(
            client.post(resolved_url, json=payload),
            timeout_seconds=DEFAULT_NOTIFICATION_TIMEOUT_SECONDS + 5.0,
        )
        response.raise_for_status()
        return True
    except Exception:
        logger.warning("Failed to send webhook notification to %s", resolved_url, exc_info=True)
        if reserved_at is not None:
            await _release_event(resolved_event_key, reserved_at)
        return False
    finally:
        await _wait(
            client.aclose(),
            timeout_seconds=DEFAULT_NOTIFICATION_TIMEOUT_SECONDS + 5.0,
        )
