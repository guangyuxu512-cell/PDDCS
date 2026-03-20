"""拼多多客服页 DOM 探测工具。"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from playwright.async_api import (
    BrowserContext,
    Locator,
    Page,
    Playwright,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)

from backend.adapters.pdd import PDD_CHAT_URL, SELECTORS
from backend.engines.playwright_engine import LAUNCH_TIMEOUT_SECONDS
from backend.engines.profile_factory import ProfileFactory


logger = logging.getLogger(__name__)

RESULT_PATH = Path(__file__).resolve().parent / "pdd_selectors_result.json"
DEFAULT_TIMEOUT_SECONDS = 10.0
LOGIN_WAIT_TIMEOUT_MS = 120000
PROBE_SHOP_ID = "probe-test"
PROBE_OUTPUT_KEYS = (
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
METHOD_ORDER = ("data-testid", "aria-label", "class", "tag+class", "text", "structure")
TEXT_TARGET_TAGS = {"a", "button", "div", "label", "span"}
STRUCTURE_TEXT_JS = """
(element, mode) => {
  const isVisible = (node) => {
    if (!node) return false;
    const rect = node.getBoundingClientRect();
    const style = window.getComputedStyle(node);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };

  const normalize = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const descendants = Array.from(element.querySelectorAll('*'))
    .filter(isVisible)
    .map((node) => ({
      tag: node.tagName.toLowerCase(),
      dataTestId: node.getAttribute('data-testid') || '',
      ariaLabel: node.getAttribute('aria-label') || '',
      classes: Array.from(node.classList || []),
      text: normalize(node.innerText || node.textContent || ''),
      outerHtml: node.outerHTML || '',
      role: node.getAttribute('role') || '',
      placeholder: node.getAttribute('placeholder') || '',
      contenteditable: node.getAttribute('contenteditable') || '',
    }))
    .filter((node) => node.text);

  if (!descendants.length) {
    return null;
  }

  descendants.sort((left, right) => {
    if (mode === 'shortest') {
      return left.text.length - right.text.length;
    }
    return right.text.length - left.text.length;
  });

  return descendants[0];
}
"""
PARENT_HTML_JS = """
(element) => {
  const parent = element?.parentElement;
  return parent ? parent.outerHTML || '' : element?.outerHTML || '';
}
"""
ELEMENT_METADATA_JS = """
(element) => ({
  tag: element.tagName.toLowerCase(),
  dataTestId: element.getAttribute('data-testid') || '',
  ariaLabel: element.getAttribute('aria-label') || '',
  classes: Array.from(element.classList || []),
  text: (element.innerText || element.textContent || '').replace(/\\s+/g, ' ').trim(),
  outerHtml: element.outerHTML || '',
  role: element.getAttribute('role') || '',
  placeholder: element.getAttribute('placeholder') || '',
  contenteditable: element.getAttribute('contenteditable') || '',
})
"""


SelectorMethod = Literal["data-testid", "aria-label", "class", "tag+class", "text", "structure", "not_found"]


@dataclass(slots=True)
class ElementMetadata:
    tag: str
    data_test_id: str = ""
    aria_label: str = ""
    classes: tuple[str, ...] = ()
    text: str = ""
    outer_html: str = ""
    role: str = ""
    placeholder: str = ""
    contenteditable: str = ""


@dataclass(slots=True)
class ProbeTarget:
    key: str
    label: str
    queries: dict[str, tuple[str, ...]]
    class_hints: tuple[str, ...]


@dataclass(slots=True)
class ProbeHit:
    key: str
    selector: str
    method: SelectorMethod
    count: int
    locator: Locator | None = None
    metadata: ElementMetadata | None = None

    def to_result_dict(self) -> dict[str, Any]:
        return {"selector": self.selector, "method": self.method, "count": self.count}


def _resolve_chrome_path() -> str:
    return os.getenv("CHROME_PATH", "").strip() or os.getenv("CHROME_EXECUTABLE_PATH", "").strip()


async def _wait(awaitable: Any, timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS) -> Any:
    return await asyncio.wait_for(awaitable, timeout=timeout_seconds)


async def _has_any_selector(page: Page, selector_key: str) -> bool:
    for selector in SELECTORS[selector_key].all():
        try:
            count = await _wait(page.locator(selector).count(), timeout_seconds=5.0)
        except Exception:
            continue
        if count > 0:
            return True
    return False


async def _wait_for_any_selector(page: Page, selector_key: str, timeout_ms: int) -> bool:
    selectors = SELECTORS[selector_key].all()
    per_selector_timeout_ms = max(timeout_ms // max(len(selectors), 1), 1)
    for selector in selectors:
        try:
            handle = await _wait(
                page.wait_for_selector(selector, timeout=per_selector_timeout_ms),
                timeout_seconds=max((per_selector_timeout_ms / 1000) + 1.0, 1.0),
            )
        except (PlaywrightTimeoutError, TimeoutError):
            continue
        if handle is not None:
            return True
    return False


def _normalize_text(value: str, max_length: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def _normalize_html(value: str, max_length: int = 600) -> str:
    normalized = re.sub(r"\s+", " ", value).strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[: max_length - 3]}..."


def _escape_css_value(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _is_stable_class(class_name: str) -> bool:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,40}", class_name):
        return False
    if re.search(r"\d{6,}", class_name):
        return False
    if re.fullmatch(r"css-[A-Za-z0-9]{6,}", class_name):
        return False
    if re.fullmatch(r"[A-Fa-f0-9]{8,}", class_name):
        return False
    return True


def extract_stable_classes(class_names: tuple[str, ...], hints: tuple[str, ...]) -> list[str]:
    stable_classes = [class_name for class_name in class_names if _is_stable_class(class_name)]
    lowered_hints = tuple(hint.lower() for hint in hints)
    return sorted(
        stable_classes,
        key=lambda class_name: (
            not any(hint in class_name.lower() for hint in lowered_hints),
            len(class_name),
            class_name,
        ),
    )


def build_selector_candidates(
    metadata: ElementMetadata,
    class_hints: tuple[str, ...] = (),
) -> list[tuple[str, SelectorMethod]]:
    candidates: list[tuple[str, SelectorMethod]] = []
    if metadata.data_test_id:
        candidates.append((f"[data-testid='{_escape_css_value(metadata.data_test_id)}']", "data-testid"))
    if metadata.aria_label:
        candidates.append((f"[aria-label='{_escape_css_value(metadata.aria_label)}']", "aria-label"))

    stable_classes = extract_stable_classes(metadata.classes, class_hints)
    if stable_classes:
        candidates.append((f".{stable_classes[0]}", "class"))
        if metadata.tag:
            candidates.append((f"{metadata.tag}.{stable_classes[0]}", "tag+class"))

    short_text = _normalize_text(metadata.text, max_length=20)
    if metadata.tag in TEXT_TARGET_TAGS and short_text:
        candidates.append((f"{metadata.tag}:has-text('{_escape_css_value(short_text)}')", "text"))

    if metadata.placeholder and metadata.tag:
        candidates.append(
            (
                f"{metadata.tag}[placeholder='{_escape_css_value(metadata.placeholder)}']",
                "structure",
            )
        )
    if metadata.contenteditable.lower() == "true" and metadata.tag:
        candidates.append((f"{metadata.tag}[contenteditable='true']", "structure"))
    if metadata.role and metadata.tag:
        candidates.append((f"{metadata.tag}[role='{_escape_css_value(metadata.role)}']", "structure"))
    if metadata.tag == "textarea":
        candidates.append(("textarea", "structure"))
    if metadata.tag:
        candidates.append((metadata.tag, "structure"))

    deduplicated: list[tuple[str, SelectorMethod]] = []
    seen: set[str] = set()
    for selector, method in candidates:
        if selector in seen:
            continue
        seen.add(selector)
        deduplicated.append((selector, method))
    return deduplicated


def _build_not_found_hit(key: str) -> ProbeHit:
    return ProbeHit(key=key, selector="", method="not_found", count=0)


def _metadata_from_dict(data: dict[str, Any]) -> ElementMetadata:
    return ElementMetadata(
        tag=str(data.get("tag", "")).lower(),
        data_test_id=str(data.get("dataTestId", "")),
        aria_label=str(data.get("ariaLabel", "")),
        classes=tuple(str(item) for item in data.get("classes", []) if str(item)),
        text=_normalize_text(str(data.get("text", "")), max_length=120),
        outer_html=_normalize_html(str(data.get("outerHtml", "")), max_length=600),
        role=str(data.get("role", "")),
        placeholder=str(data.get("placeholder", "")),
        contenteditable=str(data.get("contenteditable", "")),
    )


async def _extract_metadata(locator: Locator) -> ElementMetadata:
    data = await _wait(locator.evaluate(ELEMENT_METADATA_JS), timeout_seconds=5.0)
    return _metadata_from_dict(data)


async def _resolve_selector(
    page: Page,
    metadata: ElementMetadata,
    class_hints: tuple[str, ...],
) -> tuple[str, SelectorMethod, int]:
    for selector, method in build_selector_candidates(metadata, class_hints=class_hints):
        try:
            count = await _wait(page.locator(selector).count(), timeout_seconds=5.0)
        except Exception:
            continue
        if count > 0:
            return selector, method, count
    return "", "not_found", 0


async def _locator_from_queries(root: Page | Locator, queries: tuple[str, ...]) -> Locator | None:
    for query in queries:
        try:
            locator = root.locator(query)
            count = await _wait(locator.count(), timeout_seconds=5.0)
        except Exception:
            continue
        if count > 0:
            return locator.first
    return None


async def _locator_for_text_descendant(scope: Locator, mode: Literal["shortest", "longest"]) -> ElementMetadata | None:
    try:
        data = await _wait(scope.evaluate(STRUCTURE_TEXT_JS, mode), timeout_seconds=5.0)
    except Exception:
        return None
    if not data:
        return None
    return _metadata_from_dict(data)


async def _probe_target(page: Page, target: ProbeTarget, scope: Page | Locator | None = None) -> ProbeHit:
    root = scope or page
    for method_name in METHOD_ORDER:
        queries = target.queries.get(method_name, ())
        locator = await _locator_from_queries(root, queries)
        if locator is None:
            continue
        metadata = await _extract_metadata(locator)
        selector, resolved_method, count = await _resolve_selector(page, metadata, target.class_hints)
        if selector:
            return ProbeHit(
                key=target.key,
                selector=selector,
                method=resolved_method,
                count=count,
                locator=locator,
                metadata=metadata,
            )
    return _build_not_found_hit(target.key)


async def _probe_text_descendant_target(
    page: Page,
    key: str,
    class_hints: tuple[str, ...],
    scope: Locator | None,
    mode: Literal["shortest", "longest"],
) -> ProbeHit:
    if scope is None:
        return _build_not_found_hit(key)

    metadata = await _locator_for_text_descendant(scope, mode=mode)
    if metadata is None:
        return _build_not_found_hit(key)

    selector, method, count = await _resolve_selector(page, metadata, class_hints)
    if not selector:
        return _build_not_found_hit(key)
    return ProbeHit(
        key=key,
        selector=selector,
        method=method,
        count=count,
        locator=scope,
        metadata=metadata,
    )


async def _safe_outer_html(locator: Locator | None, parent: bool = False) -> str:
    if locator is None:
        return ""
    try:
        if parent:
            html = await _wait(locator.evaluate(PARENT_HTML_JS), timeout_seconds=5.0)
        else:
            html = await _wait(locator.evaluate("(element) => element.outerHTML || ''"), timeout_seconds=5.0)
    except Exception:
        return ""
    return _normalize_html(str(html), max_length=600)


def _probe_targets() -> dict[str, ProbeTarget]:
    return {
        "session_list": ProbeTarget(
            key="session_list",
            label="会话列表容器",
            class_hints=("session", "chat", "list", "conversation"),
            queries={
                "data-testid": (
                    "[data-testid*='session' i]",
                    "[data-testid*='chat-list' i]",
                    "[data-testid*='conversation' i]",
                ),
                "aria-label": (
                    "[aria-label*='会话' i]",
                    "[aria-label*='聊天' i]",
                    "[aria-label*='session' i]",
                ),
                "class": (
                    ".chat-list",
                    ".session-list",
                    "[class*='chatList']",
                    "[class*='sessionList']",
                    "[class*='conversation']",
                ),
                "tag+class": (
                    "aside[class*='chat']",
                    "aside[class*='session']",
                    "nav[class*='session']",
                    "div[class*='session']",
                ),
                "text": (),
                "structure": (
                    "aside",
                    "nav",
                    "xpath=//*[self::aside or self::nav][count(.//*[self::div or self::li]) >= 3]",
                ),
            },
        ),
        "session_item": ProbeTarget(
            key="session_item",
            label="单个会话项",
            class_hints=("session", "item", "chat", "conversation"),
            queries={
                "data-testid": (
                    "[data-testid*='session-item' i]",
                    "[data-testid*='conversation-item' i]",
                ),
                "aria-label": (
                    "[aria-label*='会话' i]",
                    "[aria-label*='session' i]",
                ),
                "class": (
                    ".chat-list-item",
                    ".session-item",
                    "[class*='chatListItem']",
                    "[class*='sessionItem']",
                ),
                "tag+class": (
                    "li[class]",
                    "div[class*='item']",
                    "div[class*='session']",
                ),
                "text": (),
                "structure": (
                    "xpath=./*[self::div or self::li]",
                    "xpath=.//*[self::div or self::li][count(.//*[normalize-space()]) > 0]",
                ),
            },
        ),
        "buyer_name": ProbeTarget(
            key="buyer_name",
            label="会话项中的买家名",
            class_hints=("buyer", "nick", "name", "user"),
            queries={
                "data-testid": ("[data-testid*='buyer' i]", "[data-testid*='nickname' i]"),
                "aria-label": ("[aria-label*='买家' i]", "[aria-label*='昵称' i]"),
                "class": (
                    ".buyer-name",
                    ".nick-name",
                    "[class*='buyerName']",
                    "[class*='nickName']",
                    "[class*='userName']",
                ),
                "tag+class": ("span[class*='name']", "div[class*='name']"),
                "text": (),
                "structure": (),
            },
        ),
        "last_message": ProbeTarget(
            key="last_message",
            label="会话项中的消息预览",
            class_hints=("msg", "message", "preview", "last"),
            queries={
                "data-testid": ("[data-testid*='preview' i]", "[data-testid*='message' i]"),
                "aria-label": ("[aria-label*='消息' i]", "[aria-label*='预览' i]"),
                "class": (
                    ".last-msg",
                    ".msg-preview",
                    "[class*='lastMsg']",
                    "[class*='msgPreview']",
                ),
                "tag+class": ("span[class*='msg']", "div[class*='preview']", "div[class*='msg']"),
                "text": (),
                "structure": (),
            },
        ),
        "unread_badge": ProbeTarget(
            key="unread_badge",
            label="未读消息标记",
            class_hints=("unread", "badge", "count"),
            queries={
                "data-testid": ("[data-testid*='unread' i]", "[data-testid*='badge' i]"),
                "aria-label": ("[aria-label*='未读' i]", "[aria-label*='unread' i]"),
                "class": (
                    ".unread-badge",
                    ".badge",
                    "[class*='unread']",
                    "[class*='badge']",
                ),
                "tag+class": ("span[class*='badge']", "div[class*='badge']", "span[class*='unread']"),
                "text": ("text=/^\\d+$/", "text=未读"),
                "structure": (),
            },
        ),
        "message_container": ProbeTarget(
            key="message_container",
            label="消息容器",
            class_hints=("message", "msg", "chat", "content"),
            queries={
                "data-testid": ("[data-testid*='message-list' i]", "[data-testid*='chat-content' i]"),
                "aria-label": ("[aria-label*='消息' i]", "[aria-label*='聊天内容' i]"),
                "class": (
                    ".chat-content",
                    ".message-list",
                    "[class*='chatContent']",
                    "[class*='messageList']",
                    "[class*='msgList']",
                ),
                "tag+class": (
                    "section[class*='message']",
                    "div[class*='message']",
                    "div[class*='chat']",
                ),
                "text": (),
                "structure": (
                    "main",
                    "section",
                    "xpath=//*[self::main or self::section or self::div][count(.//*[self::div or self::li]) >= 3]",
                ),
            },
        ),
        "message_item": ProbeTarget(
            key="message_item",
            label="单条消息元素",
            class_hints=("message", "msg", "item", "bubble"),
            queries={
                "data-testid": ("[data-testid*='message-item' i]", "[data-testid*='msg-item' i]"),
                "aria-label": ("[aria-label*='消息' i]",),
                "class": (
                    ".msg-item",
                    ".message-item",
                    "[class*='msgItem']",
                    "[class*='messageItem']",
                ),
                "tag+class": ("div[class*='msg']", "div[class*='message']", "li[class*='message']"),
                "text": (),
                "structure": (
                    "xpath=./*[self::div or self::li]",
                    "xpath=.//*[self::div or self::li][normalize-space()]",
                ),
            },
        ),
        "message_text": ProbeTarget(
            key="message_text",
            label="消息文本内容",
            class_hints=("text", "content", "msg"),
            queries={
                "data-testid": ("[data-testid*='message-text' i]", "[data-testid*='content' i]"),
                "aria-label": ("[aria-label*='消息内容' i]",),
                "class": (
                    ".msg-text",
                    ".text-content",
                    "[class*='msgText']",
                    "[class*='textContent']",
                    "[class*='msgContent']",
                ),
                "tag+class": ("span[class*='text']", "div[class*='text']", "div[class*='content']"),
                "text": (),
                "structure": (),
            },
        ),
        "message_sender_buyer": ProbeTarget(
            key="message_sender_buyer",
            label="买家消息特征",
            class_hints=("buyer", "left", "receive"),
            queries={
                "data-testid": ("[data-testid*='buyer' i]", "[data-testid*='receive' i]"),
                "aria-label": ("[aria-label*='买家' i]",),
                "class": (
                    ".buyer-msg",
                    ".msg-left",
                    "[class*='buyerMsg']",
                    "[class*='msgLeft']",
                    "[class*='receive']",
                ),
                "tag+class": ("div[class*='buyer']", "div[class*='left']", "div[class*='receive']"),
                "text": (),
                "structure": (),
            },
        ),
        "message_sender_self": ProbeTarget(
            key="message_sender_self",
            label="客服消息特征",
            class_hints=("self", "right", "send"),
            queries={
                "data-testid": ("[data-testid*='self' i]", "[data-testid*='send' i]"),
                "aria-label": ("[aria-label*='客服' i]", "[aria-label*='发送' i]"),
                "class": (
                    ".self-msg",
                    ".msg-right",
                    "[class*='selfMsg']",
                    "[class*='msgRight']",
                    "[class*='send']",
                ),
                "tag+class": ("div[class*='self']", "div[class*='right']", "div[class*='send']"),
                "text": (),
                "structure": (),
            },
        ),
        "input_box": ProbeTarget(
            key="input_box",
            label="文本输入框",
            class_hints=("input", "editor", "textarea"),
            queries={
                "data-testid": ("[data-testid*='input' i]", "[data-testid*='editor' i]"),
                "aria-label": ("[aria-label*='输入' i]", "[aria-label*='消息' i]"),
                "class": (
                    ".chat-input textarea",
                    ".msg-input textarea",
                    "[class*='chatInput'] textarea",
                    "[class*='editorInner']",
                    "textarea[class*='input']",
                ),
                "tag+class": (
                    "textarea",
                    "div[contenteditable='true']",
                    "div[class*='editor']",
                ),
                "text": (),
                "structure": (
                    "textarea",
                    "div[contenteditable='true']",
                    "xpath=//*[self::textarea or @contenteditable='true']",
                ),
            },
        ),
        "send_button": ProbeTarget(
            key="send_button",
            label="发送按钮",
            class_hints=("send", "submit", "button"),
            queries={
                "data-testid": ("[data-testid*='send' i]", "[data-testid*='submit' i]"),
                "aria-label": ("[aria-label*='发送' i]", "[aria-label*='提交' i]"),
                "class": (".send-btn", ".btn-send", "[class*='sendBtn']", "button[class*='send']"),
                "tag+class": ("button[class*='send']", "div[class*='send']"),
                "text": ("button:has-text('发送')", "[role='button']:has-text('发送')"),
                "structure": ("button", "[role='button']"),
            },
        ),
        "transfer_button": ProbeTarget(
            key="transfer_button",
            label="转接/转人工按钮",
            class_hints=("transfer", "escalat", "human"),
            queries={
                "data-testid": ("[data-testid*='transfer' i]", "[data-testid*='escalat' i]"),
                "aria-label": ("[aria-label*='转接' i]", "[aria-label*='转人工' i]"),
                "class": (".transfer-btn", "[class*='transfer']", "[class*='escalat']"),
                "tag+class": ("button[class*='transfer']", "div[class*='transfer']"),
                "text": (
                    "button:has-text('转人工')",
                    "button:has-text('转接')",
                    "[role='button']:has-text('转人工')",
                    "[role='button']:has-text('转接')",
                ),
                "structure": ("button", "[role='button']"),
            },
        ),
    }


async def probe_page(page: Page) -> dict[str, Any]:
    targets = _probe_targets()

    session_list_hit = await _probe_target(page, targets["session_list"])
    session_item_scope = session_list_hit.locator if session_list_hit.locator is not None else None
    session_item_hit = await _probe_target(page, targets["session_item"], scope=session_item_scope)
    session_item_locator = session_item_hit.locator

    buyer_name_hit = await _probe_target(page, targets["buyer_name"], scope=session_item_locator)
    if buyer_name_hit.method == "not_found":
        buyer_name_hit = await _probe_text_descendant_target(
            page,
            key="buyer_name",
            class_hints=targets["buyer_name"].class_hints,
            scope=session_item_locator,
            mode="shortest",
        )

    last_message_hit = await _probe_target(page, targets["last_message"], scope=session_item_locator)
    if last_message_hit.method == "not_found":
        last_message_hit = await _probe_text_descendant_target(
            page,
            key="last_message",
            class_hints=targets["last_message"].class_hints,
            scope=session_item_locator,
            mode="longest",
        )

    unread_badge_hit = await _probe_target(page, targets["unread_badge"], scope=session_item_locator)

    message_container_hit = await _probe_target(page, targets["message_container"])
    message_item_scope = message_container_hit.locator if message_container_hit.locator is not None else None
    message_item_hit = await _probe_target(page, targets["message_item"], scope=message_item_scope)
    message_item_locator = message_item_hit.locator

    message_text_hit = await _probe_target(page, targets["message_text"], scope=message_item_locator)
    if message_text_hit.method == "not_found":
        message_text_hit = await _probe_text_descendant_target(
            page,
            key="message_text",
            class_hints=targets["message_text"].class_hints,
            scope=message_item_locator,
            mode="longest",
        )

    message_sender_buyer_hit = await _probe_target(
        page,
        targets["message_sender_buyer"],
        scope=message_container_hit.locator,
    )
    message_sender_self_hit = await _probe_target(
        page,
        targets["message_sender_self"],
        scope=message_container_hit.locator,
    )
    input_box_hit = await _probe_target(page, targets["input_box"])
    send_button_hit = await _probe_target(page, targets["send_button"])
    transfer_button_hit = await _probe_target(page, targets["transfer_button"])

    return {
        "session_list": session_list_hit.to_result_dict(),
        "session_item": session_item_hit.to_result_dict(),
        "buyer_name": buyer_name_hit.to_result_dict(),
        "last_message": last_message_hit.to_result_dict(),
        "unread_badge": unread_badge_hit.to_result_dict(),
        "message_container": message_container_hit.to_result_dict(),
        "message_item": message_item_hit.to_result_dict(),
        "message_text": message_text_hit.to_result_dict(),
        "message_sender_buyer": message_sender_buyer_hit.to_result_dict(),
        "message_sender_self": message_sender_self_hit.to_result_dict(),
        "input_box": input_box_hit.to_result_dict(),
        "send_button": send_button_hit.to_result_dict(),
        "transfer_button": transfer_button_hit.to_result_dict(),
        "_raw_html_snippets": {
            "session_item_sample": await _safe_outer_html(session_item_locator),
            "message_item_sample": await _safe_outer_html(message_item_locator),
            "input_area_sample": await _safe_outer_html(input_box_hit.locator, parent=True),
        },
    }


def _print_results(results: dict[str, Any]) -> None:
    print("\n=== PDD DOM Probe Result ===")
    for key in PROBE_OUTPUT_KEYS:
        item = results.get(key, {})
        selector = item.get("selector", "")
        method = item.get("method", "not_found")
        count = item.get("count", 0)
        print(f"{key}: selector={selector or '<not found>'} | method={method} | count={count}")
    print("结果已写入:", RESULT_PATH)


def _write_results(results: dict[str, Any]) -> None:
    RESULT_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


async def _launch_context(playwright: Playwright) -> BrowserContext:
    user_data_dir = ProfileFactory().get_or_create(PROBE_SHOP_ID)

    launch_kwargs: dict[str, Any] = {
        "channel": "chrome",
        "headless": False,
        "no_viewport": True,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--start-maximized",
        ],
    }
    chrome_executable_path = _resolve_chrome_path()
    if chrome_executable_path:
        launch_kwargs["executable_path"] = chrome_executable_path
        launch_kwargs.pop("channel", None)

    context = await _wait(
        playwright.chromium.launch_persistent_context(user_data_dir, **launch_kwargs),
        timeout_seconds=LAUNCH_TIMEOUT_SECONDS,
    )
    return context


async def _ensure_page(context: BrowserContext) -> Page:
    if context.pages:
        return context.pages[0]
    return await _wait(context.new_page(), timeout_seconds=10.0)


async def _navigate_to_chat(page: Page) -> None:
    await _wait(
        page.goto(PDD_CHAT_URL, wait_until="domcontentloaded", timeout=30000),
        timeout_seconds=35.0,
    )
    try:
        await _wait(page.wait_for_load_state("networkidle", timeout=10000), timeout_seconds=12.0)
    except Exception:
        logger.info("Network idle wait skipped")


async def _ensure_logged_in(page: Page) -> bool:
    if await _has_any_selector(page, "session_list"):
        return True

    print("未检测到登录态，请在 2 分钟内手动登录...")
    if await _wait_for_any_selector(page, "session_list", timeout_ms=LOGIN_WAIT_TIMEOUT_MS):
        return True
    return False


async def _read_command() -> str:
    try:
        return await asyncio.to_thread(input, "按 Enter 重新探测，输入 q 退出: ")
    except EOFError:
        return "q"


async def run_probe() -> int:
    logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [%(levelname)s] %(message)s")
    chrome_path = _resolve_chrome_path()
    if chrome_path:
        print(f"提示：将使用配置的 Chrome 路径: {chrome_path}")
    else:
        print("提示：将通过 channel='chrome' 启动系统安装的 Chrome")

    playwright = await _wait(async_playwright().start(), timeout_seconds=LAUNCH_TIMEOUT_SECONDS)
    context: BrowserContext | None = None
    try:
        context = await _launch_context(playwright)
        page = await _ensure_page(context)
        await _navigate_to_chat(page)
        if not await _ensure_logged_in(page):
            print("登录超时，脚本退出。")
            return 1

        while True:
            results = await probe_page(page)
            _print_results(results)
            _write_results(results)
            command = (await _read_command()).strip().lower()
            if command == "q":
                return 0
    finally:
        if context is not None:
            await _wait(context.close(), timeout_seconds=15.0)
        await _wait(playwright.stop(), timeout_seconds=10.0)


def main() -> int:
    return asyncio.run(run_probe())


if __name__ == "__main__":
    raise SystemExit(main())
