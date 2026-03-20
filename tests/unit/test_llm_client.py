from __future__ import annotations

import httpx
import pytest

from backend.ai.llm_client import LlmClient, create_llm_client_from_settings


class _FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200, text: str = "") -> None:
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "https://example.com/v1/chat/completions")
            response = httpx.Response(self.status_code, request=request, text=self.text)
            raise httpx.HTTPStatusError("request failed", request=request, response=response)

    def json(self) -> dict[str, object]:
        return self._payload


@pytest.mark.asyncio
async def test_chat_returns_fallback_when_client_not_configured() -> None:
    client = LlmClient(api_base_url="", api_key="", model="")
    result = await client.chat(messages=[{"role": "user", "content": "你好"}], fallback="兜底回复")
    assert result == "兜底回复"


@pytest.mark.asyncio
async def test_chat_retries_after_timeout_and_returns_content(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = {"count": 0}

    async def fake_post(self: LlmClient, payload: dict[str, object], headers: dict[str, str]) -> _FakeResponse:
        del payload, headers
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.TimeoutException("timeout")
        return _FakeResponse({"choices": [{"message": {"content": "测试成功"}}]})

    monkeypatch.setattr(LlmClient, "_post_chat_completion", fake_post)
    client = LlmClient(
        api_base_url="https://api.openai.com",
        api_key="sk-live",
        model="gpt-test",
        timeout_seconds=1.0,
        max_retries=2,
        retry_backoff_seconds=(0.0,),
    )

    result = await client.chat(messages=[{"role": "user", "content": "你好"}])
    assert result == "测试成功"
    assert attempts["count"] == 2


@pytest.mark.asyncio
async def test_test_connection_returns_error_when_parameters_missing() -> None:
    client = LlmClient(api_base_url="https://api.openai.com", api_key="sk-live", model="")
    result = await client.test_connection()
    assert result == {"ok": False, "message": "参数不完整"}


@pytest.mark.asyncio
async def test_test_connection_skips_live_probe_for_demo_credentials() -> None:
    client = LlmClient(api_base_url="https://api.openai.com", api_key="sk-test", model="gpt-5-mini")
    result = await client.test_connection()
    assert result["ok"] is True
    assert "gpt-5-mini" in result["message"]


def test_create_llm_client_uses_shop_custom_config() -> None:
    client = create_llm_client_from_settings(
        settings={
            "apiBaseUrl": "https://api.openai.com/v1",
            "apiKey": "sk-global",
            "defaultModel": "gpt-global",
            "temperature": 0.3,
            "maxTokens": 256,
        },
        shop_config={
            "llmMode": "custom",
            "customApiKey": "sk-shop",
            "customModel": "gpt-shop",
        },
    )
    assert client.api_key == "sk-shop"
    assert client.model == "gpt-shop"
    assert client.chat_url == "https://api.openai.com/v1/chat/completions"
