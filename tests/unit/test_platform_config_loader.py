from __future__ import annotations

from config.platforms import get_platform_config, get_platform_selector_values


def test_get_platform_config_returns_pdd_urls_and_selector_groups() -> None:
    config = get_platform_config("pdd")
    selectors = get_platform_selector_values("pdd")

    assert config["chat_url"] == "https://mms.pinduoduo.com/chat-merchant/#/"
    assert config["login_url"] == "https://mms.pinduoduo.com/login/"
    assert selectors["input_box"][0] == "textarea#replyTextarea"
    assert selectors["session_timeout_item"] == ("ul.timeout-unreply li.chat-item",)
    assert "message_list_item" in selectors
