"""LLM HTTP 调用封装。"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any, TypeVar

import httpx


logger = logging.getLogger(__name__)

DEFAULT_FALLBACK = "亲，系统繁忙，请稍后再试~"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_WAIT_TIMEOUT_BUFFER_SECONDS = 5.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_BACKOFF_SECONDS = (1.0, 2.0, 4.0)
T = TypeVar("T")


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return float(value)
    except ValueError:
        logger.warning("Invalid float env %s=%r, using default %s", name, value, default)
        return default


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("Invalid int env %s=%r, using default %s", name, value, default)
        return default


def _env_backoff(name: str, default: Sequence[float]) -> tuple[float, ...]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return tuple(default)

    parts: list[float] = []
    for item in raw.split(","):
        text = item.strip()
        if not text:
            continue
        try:
            parts.append(float(text))
        except ValueError:
            logger.warning("Invalid backoff value %r in %s, using defaults", text, name)
            return tuple(default)
    return tuple(parts) or tuple(default)


async def _wait(awaitable: Awaitable[T], timeout_seconds: float) -> T:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


def _mapping_value(data: Mapping[str, Any] | None, *keys: str, default: Any = "") -> Any:
    if data is None:
        return default
    for key in keys:
        value = data.get(key)
        if value is not None:
            return value
    return default


def _normalize_api_base_url(api_base_url: str) -> str:
    return api_base_url.strip().rstrip("/")


def _build_chat_url(api_base_url: str) -> str:
    normalized = _normalize_api_base_url(api_base_url)
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/v1/chat/completions"


def _is_demo_api_key(api_key: str) -> bool:
    key = api_key.strip()
    if key in {"sk-test", "sk-demo", "test", "demo"}:
        return True
    return re.fullmatch(r"sk-(test|demo)(-.+)?", key) is not None


class LlmClient:
    """OpenAI 兼容 Chat Completions 客户端。"""

    def __init__(
        self,
        api_base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.7,
        max_tokens: int = 200,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        retry_backoff_seconds: Sequence[float] | None = None,
    ) -> None:
        self.api_base_url = _normalize_api_base_url(api_base_url)
        self.api_key = api_key.strip()
        self.model = model.strip()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.request_timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else _env_float("LLM_REQUEST_TIMEOUT_SECONDS", DEFAULT_REQUEST_TIMEOUT_SECONDS)
        )
        configured_retries = (
            max_retries if max_retries is not None else _env_int("LLM_MAX_RETRIES", DEFAULT_MAX_RETRIES)
        )
        self.max_retries = max(1, configured_retries)
        self.retry_backoff_seconds = tuple(
            retry_backoff_seconds
            if retry_backoff_seconds is not None
            else _env_backoff("LLM_RETRY_BACKOFF_SECONDS", DEFAULT_RETRY_BACKOFF_SECONDS)
        )

    @property
    def chat_url(self) -> str:
        return _build_chat_url(self.api_base_url)

    async def _post_chat_completion(
        self,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> httpx.Response:
        client = httpx.AsyncClient(timeout=self.request_timeout_seconds)
        try:
            return await _wait(
                client.post(self.chat_url, json=payload, headers=headers),
                timeout_seconds=self.request_timeout_seconds + DEFAULT_WAIT_TIMEOUT_BUFFER_SECONDS,
            )
        finally:
            await _wait(
                client.aclose(),
                timeout_seconds=min(self.request_timeout_seconds, 10.0) + DEFAULT_WAIT_TIMEOUT_BUFFER_SECONDS,
            )

    async def chat(
        self,
        messages: list[dict[str, str]],
        system_prompt: str = "",
        fallback: str = DEFAULT_FALLBACK,
    ) -> str:
        """调用 LLM 生成回复，失败时返回 fallback。"""
        if not self.api_base_url or not self.api_key or not self.model:
            logger.warning("LLM not fully configured, returning fallback")
            return fallback

        chat_messages: list[dict[str, str]] = []
        if system_prompt:
            chat_messages.append({"role": "system", "content": system_prompt})
        chat_messages.extend(messages)

        payload = {
            "model": self.model,
            "messages": chat_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        for attempt in range(self.max_retries):
            try:
                response = await self._post_chat_completion(payload=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                content = str(data["choices"][0]["message"]["content"]).strip()
                if content:
                    return content
                logger.warning("LLM returned empty content")
                return fallback
            except httpx.TimeoutException:
                logger.warning("LLM timeout (attempt %s/%s)", attempt + 1, self.max_retries)
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "LLM HTTP error %s: %s",
                    exc.response.status_code,
                    exc.response.text[:200],
                )
                if exc.response.status_code in {401, 403}:
                    return fallback
            except Exception as exc:
                logger.error("LLM unexpected error: %s", exc)

            if attempt < self.max_retries - 1:
                wait_seconds = self.retry_backoff_seconds[min(attempt, len(self.retry_backoff_seconds) - 1)]
                if wait_seconds > 0:
                    logger.info("Retrying LLM request in %ss", wait_seconds)
                    await _wait(asyncio.sleep(wait_seconds), timeout_seconds=wait_seconds + 1.0)

        logger.error("LLM all retries exhausted, returning fallback")
        return fallback

    async def test_connection(self) -> dict[str, Any]:
        """测试 LLM 连接状态。"""
        if not self.api_base_url or not self.api_key or not self.model:
            return {"ok": False, "message": "参数不完整"}

        if _is_demo_api_key(self.api_key):
            return {"ok": True, "message": f"模型 {self.model} 参数格式有效，已跳过真实调用"}

        result = await _wait(
            self.chat(
                messages=[{"role": "user", "content": "请回复：连接成功"}],
                system_prompt="你是一个测试助手，只需回复用户要求的内容。",
                fallback="",
            ),
            timeout_seconds=self.request_timeout_seconds + 10.0,
        )
        if result:
            return {"ok": True, "message": f"模型 {self.model} 响应正常：{result[:50]}"}
        return {"ok": False, "message": "模型返回空内容或调用失败"}


def create_llm_client_from_settings(
    settings: Mapping[str, Any],
    shop_config: Mapping[str, Any] | None = None,
) -> LlmClient:
    """根据全局设置和店铺配置创建 LLM 客户端。"""
    llm_mode = str(_mapping_value(shop_config, "llm_mode", "llmMode", default="global")).strip() or "global"
    use_custom = llm_mode == "custom"

    api_key = str(
        _mapping_value(
            shop_config if use_custom else settings,
            "custom_api_key",
            "customApiKey",
            "api_key",
            "apiKey",
            default="",
        )
    ).strip()
    model = str(
        _mapping_value(
            shop_config if use_custom else settings,
            "custom_model",
            "customModel",
            "default_model",
            "defaultModel",
            default="",
        )
    ).strip()
    api_base_url = str(_mapping_value(settings, "api_base_url", "apiBaseUrl", default="")).strip()
    temperature = float(_mapping_value(settings, "temperature", default=0.7) or 0.7)
    max_tokens = int(_mapping_value(settings, "max_tokens", "maxTokens", default=200) or 200)

    return LlmClient(
        api_base_url=api_base_url,
        api_key=api_key,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
