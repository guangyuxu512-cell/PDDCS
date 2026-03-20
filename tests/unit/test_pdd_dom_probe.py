from __future__ import annotations

import pytest

from backend.tools.pdd_dom_probe import (
    ElementMetadata,
    PROBE_OUTPUT_KEYS,
    build_selector_candidates,
    extract_stable_classes,
    _wait_for_any_selector,
)


def test_extract_stable_classes_prefers_hints_and_filters_hash_like_values() -> None:
    classes = (
        "css-1ab23cd",
        "buyer-name",
        "a8f03bc91",
        "sessionItem",
        "x123456789",
    )
    stable = extract_stable_classes(classes, hints=("buyer", "name"))
    assert stable == ["buyer-name", "sessionItem"]


def test_build_selector_candidates_prioritizes_data_attributes_before_class_and_text() -> None:
    metadata = ElementMetadata(
        tag="button",
        data_test_id="send-button",
        aria_label="发送",
        classes=("send-btn",),
        text="发送",
    )
    candidates = build_selector_candidates(metadata, class_hints=("send",))
    assert candidates[0] == ("[data-testid='send-button']", "data-testid")
    assert candidates[1] == ("[aria-label='发送']", "aria-label")
    assert (".send-btn", "class") in candidates
    assert ("button:has-text('发送')", "text") in candidates


def test_build_selector_candidates_falls_back_to_structure_for_textarea() -> None:
    metadata = ElementMetadata(tag="textarea")
    candidates = build_selector_candidates(metadata)
    assert ("textarea", "structure") in candidates


def test_probe_output_keys_cover_all_required_sections() -> None:
    assert PROBE_OUTPUT_KEYS == (
        "session_list",
        "session_item",
        "buyer_name",
        "last_message",
        "unread_badge",
        "message_container",
        "message_item",
        "message_text",
        "message_sender_buyer",
        "message_sender_self",
        "input_box",
        "send_button",
        "transfer_button",
    )


class FakeProbePage:
    def __init__(self, success_selector: str | None) -> None:
        self.success_selector = success_selector
        self.calls: list[str] = []

    async def wait_for_selector(self, selector: str, timeout: int) -> object:
        del timeout
        self.calls.append(selector)
        if selector == self.success_selector:
            return object()
        raise TimeoutError("selector not found")


@pytest.mark.asyncio
async def test_wait_for_any_selector_returns_true_when_fallback_matches() -> None:
    page = FakeProbePage(success_selector=".session-list")

    matched = await _wait_for_any_selector(page, "session_list", timeout_ms=1000)

    assert matched is True
    assert page.calls[:2] == [".chat-list", ".session-list"]


@pytest.mark.asyncio
async def test_wait_for_any_selector_returns_false_when_all_candidates_miss() -> None:
    page = FakeProbePage(success_selector=None)

    matched = await _wait_for_any_selector(page, "session_list", timeout_ms=1000)

    assert matched is False
