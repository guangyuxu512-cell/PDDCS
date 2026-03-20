from __future__ import annotations

from backend.services.escalation_checker import check_escalation


def test_keyword_match() -> None:
    result = check_escalation(
        "我要退款！",
        [{"type": "keyword", "value": "退款,投诉"}],
    )
    assert result.should_escalate is True
    assert result.rule_type == "keyword"


def test_keyword_no_match() -> None:
    result = check_escalation(
        "你好，发货了吗",
        [{"type": "keyword", "value": "退款,投诉"}],
    )
    assert result.should_escalate is False


def test_repeat_ask() -> None:
    recent = [
        {"sender": "buyer", "content": "在吗"},
        {"sender": "buyer", "content": "怎么不回复"},
    ]
    result = check_escalation(
        "到底有没有人",
        [{"type": "repeat_ask", "value": "3"}],
        recent_messages=recent,
    )
    assert result.should_escalate is True
    assert result.rule_type == "repeat_ask"


def test_order_amount() -> None:
    result = check_escalation(
        "这个订单 ¥600 的，怎么还没退",
        [{"type": "order_amount", "value": "500"}],
    )
    assert result.should_escalate is True
    assert result.rule_type == "order_amount"


def test_regex_match() -> None:
    result = check_escalation(
        "我要退货赔偿",
        [{"type": "regex", "value": "退.*赔偿"}],
    )
    assert result.should_escalate is True
    assert result.rule_type == "regex"


def test_empty_rules() -> None:
    result = check_escalation("任意消息", [])
    assert result.should_escalate is False


def test_multiple_rules_first_match_wins() -> None:
    result = check_escalation(
        "我投诉你们",
        [
            {"type": "keyword", "value": "退款"},
            {"type": "keyword", "value": "投诉"},
        ],
    )
    assert result.should_escalate is True
    assert result.rule_value == "投诉"


def test_invalid_regex_does_not_raise() -> None:
    result = check_escalation(
        "我要退款",
        [{"type": "regex", "value": "("}],
    )
    assert result.should_escalate is False
