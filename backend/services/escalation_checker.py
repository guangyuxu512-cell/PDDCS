"""转人工规则判定。"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EscalationResult:
    """转人工判定结果。"""

    should_escalate: bool
    rule_type: str = ""
    rule_value: str = ""
    matched_content: str = ""


def check_escalation(
    message_content: str,
    rules: list[dict[str, Any]],
    recent_messages: list[dict[str, Any]] | None = None,
) -> EscalationResult:
    """检查当前买家消息是否命中转人工规则。"""
    if not rules:
        return EscalationResult(should_escalate=False)

    for rule in rules:
        rule_type = str(rule.get("type", "")).strip()
        rule_value = str(rule.get("value", "")).strip()
        if not rule_type or not rule_value:
            continue

        if rule_type == "keyword":
            keywords = [keyword.strip() for keyword in rule_value.split(",") if keyword.strip()]
            for keyword in keywords:
                if keyword in message_content:
                    logger.info("Escalation triggered by keyword %s", keyword)
                    return EscalationResult(
                        should_escalate=True,
                        rule_type="keyword",
                        rule_value=keyword,
                        matched_content=message_content[:200],
                    )

        elif rule_type == "repeat_ask":
            try:
                threshold = int(rule_value)
            except ValueError:
                continue

            consecutive_buyer = 1
            for message in reversed(recent_messages or []):
                if message.get("sender") != "buyer":
                    break
                consecutive_buyer += 1

            if consecutive_buyer >= threshold:
                logger.info("Escalation triggered by repeat ask %s >= %s", consecutive_buyer, threshold)
                return EscalationResult(
                    should_escalate=True,
                    rule_type="repeat_ask",
                    rule_value=rule_value,
                    matched_content=f"连续{consecutive_buyer}条买家消息",
                )

        elif rule_type == "order_amount":
            try:
                threshold = float(rule_value)
            except ValueError:
                continue

            amounts = re.findall(r"[¥￥]?\s*(\d+(?:\.\d{1,2})?)", message_content)
            for amount_text in amounts:
                amount = float(amount_text)
                if amount >= threshold:
                    logger.info("Escalation triggered by amount %s >= %s", amount, threshold)
                    return EscalationResult(
                        should_escalate=True,
                        rule_type="order_amount",
                        rule_value=rule_value,
                        matched_content=f"金额 {amount}",
                    )

        elif rule_type == "regex":
            try:
                if re.search(rule_value, message_content):
                    logger.info("Escalation triggered by regex %s", rule_value)
                    return EscalationResult(
                        should_escalate=True,
                        rule_type="regex",
                        rule_value=rule_value,
                        matched_content=message_content[:200],
                    )
            except re.error as exc:
                logger.warning("Invalid regex %r: %s", rule_value, exc)

    return EscalationResult(should_escalate=False)
