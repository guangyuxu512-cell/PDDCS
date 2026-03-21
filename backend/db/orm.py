from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ShopTable(Base):
    __tablename__ = "shops"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    platform: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False, default="")
    password: Mapped[str] = mapped_column(Text, nullable=False, default="")
    password_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    password_hash: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cookie_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cookie_last_refresh: Mapped[str] = mapped_column(Text, nullable=False, default="")
    today_served_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default="")

    config: Mapped["ShopConfigTable | None"] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
        uselist=False,
    )
    cookie: Mapped["ShopCookieTable | None"] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
        uselist=False,
    )
    sessions: Mapped[list["SessionTable"]] = relationship(back_populates="shop", cascade="all, delete-orphan")
    escalation_logs: Mapped[list["EscalationLogTable"]] = relationship(
        back_populates="shop",
        cascade="all, delete-orphan",
    )


class ShopConfigTable(Base):
    __tablename__ = "shop_configs"

    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True)
    llm_mode: Mapped[str] = mapped_column(String, nullable=False, default="global")
    custom_api_key: Mapped[str] = mapped_column(Text, nullable=False, default="")
    custom_model: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reply_style_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    knowledge_paths: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    use_global_knowledge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    human_agent_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    escalation_rules: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    escalation_fallback_msg: Mapped[str] = mapped_column(Text, nullable=False, default="")
    auto_restart: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    force_online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default="")

    shop: Mapped[ShopTable] = relationship(back_populates="config")


class ShopCookieTable(Base):
    __tablename__ = "shop_cookies"

    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True)
    cookie_encrypted: Mapped[str] = mapped_column(Text, nullable=False, default="")
    cookie_fingerprint: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default="")

    shop: Mapped[ShopTable] = relationship(back_populates="cookie")


class SessionTable(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    shop_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    platform: Mapped[str] = mapped_column(String, nullable=False)
    buyer_id: Mapped[str] = mapped_column(String, nullable=False)
    buyer_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String, nullable=False, default="ai_processing", index=True)
    last_message_preview: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")

    shop: Mapped[ShopTable] = relationship(back_populates="sessions")
    messages: Mapped[list["MessageTable"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    escalation_logs: Mapped[list["EscalationLogTable"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
    )


class MessageTable(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sender: Mapped[str] = mapped_column(String, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dedup_key: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)

    session: Mapped[SessionTable] = relationship(back_populates="messages")


class KnowledgeFileTable(Base):
    __tablename__ = "knowledge_files"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    node_type: Mapped[str] = mapped_column(String, nullable=False)
    parent_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default="")


class SystemSettingTable(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[str] = mapped_column(Text, nullable=False, default="")


class EscalationLogTable(Base):
    __tablename__ = "escalation_logs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    shop_id: Mapped[str] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), nullable=False, index=True)
    trigger_rule_type: Mapped[str] = mapped_column(String, nullable=False)
    trigger_rule_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    matched_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    target_agent: Mapped[str] = mapped_column(Text, nullable=False, default="")
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False, default="")

    session: Mapped[SessionTable] = relationship(back_populates="escalation_logs")
    shop: Mapped[ShopTable] = relationship(back_populates="escalation_logs")


ORMTable = (
    ShopTable
    | ShopConfigTable
    | ShopCookieTable
    | SessionTable
    | MessageTable
    | KnowledgeFileTable
    | SystemSettingTable
    | EscalationLogTable
)


def orm_object_to_dict(obj: ORMTable) -> dict[str, Any]:
    return {column.name: getattr(obj, column.name) for column in obj.__table__.columns}
