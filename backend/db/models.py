"""Pydantic API models with frontend-aligned camelCase aliases."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def _parse_json_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if value == "":
        return []
    return json.loads(value)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_snake_to_camel, populate_by_name=True)

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs.setdefault("by_alias", True)
        return super().model_dump(*args, **kwargs)


Platform = Literal["pdd", "douyin", "qianniu"]
EscalationRuleType = Literal["keyword", "repeat_ask", "order_amount", "regex"]
ChatSessionStatus = Literal["ai_processing", "escalated", "closed"]
ChatMessageSender = Literal["buyer", "ai", "human"]
KnowledgeNodeType = Literal["folder", "file"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class Shop(CamelModel):
    id: str
    name: str
    platform: Platform
    is_online: bool = False
    ai_enabled: bool = False
    today_served_count: int = 0
    last_active_at: str = ""
    cookie_valid: bool = False
    has_password: bool = False
    cookie_fingerprint: str = ""


class EscalationRule(CamelModel):
    id: str
    type: EscalationRuleType
    value: str = ""


class ShopConfig(CamelModel):
    shop_id: str
    name: str
    username: str = ""
    platform: Platform = "pdd"
    cookie_valid: bool = False
    ai_enabled: bool = False
    has_password: bool = False
    cookie_fingerprint: str = ""
    llm_mode: Literal["global", "custom"] = "global"
    custom_api_key: str | None = ""
    custom_model: str | None = ""
    reply_style_note: str | None = ""
    knowledge_paths: list[str] = Field(default_factory=list)
    use_global_knowledge: bool = True
    human_agent_name: str = ""
    escalation_rules: list[EscalationRule] = Field(default_factory=list)
    escalation_fallback_msg: str = ""
    auto_restart: bool = False
    force_online: bool = False

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("knowledge_paths", "knowledgePaths"):
                if field_name in data:
                    data[field_name] = _parse_json_value(data[field_name])
            for field_name in ("escalation_rules", "escalationRules"):
                if field_name in data:
                    data[field_name] = _parse_json_value(data[field_name])
        return data


class ChatMessage(CamelModel):
    id: str
    sender: ChatMessageSender
    content: str
    created_at: str = ""


class ChatSession(CamelModel):
    id: str
    buyer_id: str
    buyer_name: str = ""
    shop_id: str
    shop_name: str = ""
    platform: Platform
    status: ChatSessionStatus = "ai_processing"
    last_message_preview: str = ""
    updated_at: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)


class DashboardSummary(CamelModel):
    today_served_count: int = 0
    ai_reply_rate: float = 0.0
    escalation_count: int = 0
    avg_first_response_ms: int = 0
    unreplied_count: int = 0
    yesterday_served_count: int = 0


class KnowledgeTreeNode(CamelModel):
    id: str
    name: str
    path: str
    node_type: KnowledgeNodeType
    children: list["KnowledgeTreeNode"] | None = None


class KnowledgeDocument(CamelModel):
    path: str
    content: str = ""
    updated_at: str = ""


class SystemSettings(CamelModel):
    api_base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    temperature: float = 0.7
    max_tokens: int = 200
    default_fallback_msg: str = ""
    default_keywords: list[str] = Field(default_factory=list)
    log_level: LogLevel = "INFO"
    history_retention_days: int = 30
    alert_webhook_url: str = ""
    max_shops: int = 10

    @model_validator(mode="before")
    @classmethod
    def parse_json_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            for field_name in ("default_keywords", "defaultKeywords"):
                if field_name in data:
                    data[field_name] = _parse_json_value(data[field_name])
        return data


class EscalationLog(CamelModel):
    id: str
    session_id: str
    shop_id: str
    trigger_rule_type: str
    trigger_rule_value: str = ""
    matched_content: str = ""
    target_agent: str = ""
    success: bool = False
    created_at: str = ""


KnowledgeTreeNode.model_rebuild()
