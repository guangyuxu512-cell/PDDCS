from __future__ import annotations

from collections.abc import Iterable

from alembic import op
import sqlalchemy as sa


revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


NOW_SQL = sa.text("CURRENT_TIMESTAMP")


SYSTEM_SETTINGS_DEFAULTS: dict[str, str] = {
    "apiBaseUrl": "",
    "apiKey": "",
    "defaultModel": "",
    "temperature": "0.7",
    "maxTokens": "200",
    "defaultFallbackMsg": "",
    "defaultKeywords": "[]",
    "logLevel": "INFO",
    "historyRetentionDays": "30",
    "alertWebhookUrl": "",
    "notifyWebhookUrl": "",
    "notifyWebhookType": "feishu",
    "maxShops": "10",
}


def _column_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _table_names() -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return set(inspector.get_table_names())


def _index_names(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _add_missing_columns(table_name: str, columns: Iterable[sa.Column[object]]) -> None:
    existing_columns = _column_names(table_name)
    with op.batch_alter_table(table_name) as batch_op:
        for column in columns:
            if column.name not in existing_columns:
                batch_op.add_column(column)


def _ensure_shops() -> None:
    if "shops" not in _table_names():
        op.create_table(
            "shops",
            sa.Column("id", sa.String(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("platform", sa.String(), nullable=False),
            sa.Column("username", sa.String(), nullable=False, server_default=""),
            sa.Column("password", sa.Text(), nullable=False, server_default=""),
            sa.Column("password_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("password_hash", sa.Text(), nullable=False, server_default=""),
            sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("ai_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cookie_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("cookie_last_refresh", sa.Text(), nullable=False, server_default=""),
            sa.Column("today_served_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_active_at", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=NOW_SQL),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        )
        return

    _add_missing_columns(
        "shops",
        [
            sa.Column("password", sa.Text(), nullable=False, server_default=""),
            sa.Column("password_encrypted", sa.Text(), nullable=False, server_default=""),
            sa.Column("password_hash", sa.Text(), nullable=False, server_default=""),
            sa.Column("cookie_last_refresh", sa.Text(), nullable=False, server_default=""),
            sa.Column("today_served_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_active_at", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        ],
    )


def _ensure_shop_configs() -> None:
    if "shop_configs" not in _table_names():
        op.create_table(
            "shop_configs",
            sa.Column("shop_id", sa.String(), sa.ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("llm_mode", sa.String(), nullable=False, server_default="global"),
            sa.Column("custom_api_key", sa.Text(), nullable=False, server_default=""),
            sa.Column("custom_model", sa.Text(), nullable=False, server_default=""),
            sa.Column("reply_style_note", sa.Text(), nullable=False, server_default=""),
            sa.Column("knowledge_paths", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("use_global_knowledge", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("human_agent_name", sa.Text(), nullable=False, server_default=""),
            sa.Column("escalation_rules", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("escalation_fallback_msg", sa.Text(), nullable=False, server_default=""),
            sa.Column("auto_restart", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("force_online", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        )
        return

    _add_missing_columns(
        "shop_configs",
        [
            sa.Column("auto_restart", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("force_online", sa.Boolean(), nullable=False, server_default=sa.false()),
        ],
    )


def _ensure_shop_cookies() -> None:
    if "shop_cookies" in _table_names():
        return

    op.create_table(
        "shop_cookies",
        sa.Column("shop_id", sa.String(), sa.ForeignKey("shops.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("cookie_encrypted", sa.Text(), nullable=False, server_default=""),
        sa.Column("cookie_fingerprint", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=""),
    )


def _ensure_sessions() -> None:
    if "sessions" in _table_names():
        return

    op.create_table(
        "sessions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("shop_id", sa.String(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("platform", sa.String(), nullable=False),
        sa.Column("buyer_id", sa.String(), nullable=False),
        sa.Column("buyer_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("status", sa.String(), nullable=False, server_default="ai_processing"),
        sa.Column("last_message_preview", sa.Text(), nullable=False, server_default=""),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=NOW_SQL),
    )


def _ensure_messages() -> None:
    if "messages" in _table_names():
        return

    op.create_table(
        "messages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sender", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        sa.Column("dedup_key", sa.String(), nullable=True, unique=True),
    )


def _ensure_knowledge_files() -> None:
    if "knowledge_files" in _table_names():
        return

    op.create_table(
        "knowledge_files",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False, unique=True),
        sa.Column("node_type", sa.String(), nullable=False),
        sa.Column("parent_path", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False, server_default=""),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        sa.Column("updated_at", sa.Text(), nullable=False, server_default=NOW_SQL),
    )


def _ensure_system_settings() -> None:
    bind = op.get_bind()
    if "system_settings" not in _table_names():
        op.create_table(
            "system_settings",
            sa.Column("key", sa.String(), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False, server_default=""),
            sa.Column("updated_at", sa.Text(), nullable=False, server_default=NOW_SQL),
        )

    settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String()),
        sa.column("value", sa.Text()),
        sa.column("updated_at", sa.Text()),
    )

    for key, value in SYSTEM_SETTINGS_DEFAULTS.items():
        existing = bind.execute(
            sa.select(settings_table.c.key).where(settings_table.c.key == key)
        ).scalar_one_or_none()
        if existing is None:
            bind.execute(
                settings_table.insert().values(key=key, value=value, updated_at=""),
            )


def _ensure_escalation_logs() -> None:
    if "escalation_logs" in _table_names():
        return

    op.create_table(
        "escalation_logs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("session_id", sa.String(), sa.ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("shop_id", sa.String(), sa.ForeignKey("shops.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trigger_rule_type", sa.String(), nullable=False),
        sa.Column("trigger_rule_value", sa.Text(), nullable=False, server_default=""),
        sa.Column("matched_content", sa.Text(), nullable=False, server_default=""),
        sa.Column("target_agent", sa.Text(), nullable=False, server_default=""),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.Text(), nullable=False, server_default=NOW_SQL),
    )


def _ensure_indexes() -> None:
    session_indexes = _index_names("sessions")
    if "ix_sessions_shop_id" not in session_indexes:
        op.create_index("ix_sessions_shop_id", "sessions", ["shop_id"])
    if "ix_sessions_status" not in session_indexes:
        op.create_index("ix_sessions_status", "sessions", ["status"])

    message_indexes = _index_names("messages")
    if "ix_messages_session_id" not in message_indexes:
        op.create_index("ix_messages_session_id", "messages", ["session_id"])
    if "ix_messages_dedup_key" not in message_indexes:
        op.create_index("ix_messages_dedup_key", "messages", ["dedup_key"], unique=True)

    escalation_indexes = _index_names("escalation_logs")
    if "ix_escalation_logs_session_id" not in escalation_indexes:
        op.create_index("ix_escalation_logs_session_id", "escalation_logs", ["session_id"])
    if "ix_escalation_logs_shop_id" not in escalation_indexes:
        op.create_index("ix_escalation_logs_shop_id", "escalation_logs", ["shop_id"])


def upgrade() -> None:
    _ensure_shops()
    _ensure_shop_configs()
    _ensure_shop_cookies()
    _ensure_sessions()
    _ensure_messages()
    _ensure_knowledge_files()
    _ensure_system_settings()
    _ensure_escalation_logs()
    _ensure_indexes()


def downgrade() -> None:
    for index_name in (
        "ix_escalation_logs_shop_id",
        "ix_escalation_logs_session_id",
        "ix_messages_dedup_key",
        "ix_messages_session_id",
        "ix_sessions_status",
        "ix_sessions_shop_id",
    ):
        try:
            op.drop_index(index_name)
        except Exception:
            pass

    for table_name in (
        "shop_cookies",
        "escalation_logs",
        "messages",
        "sessions",
        "system_settings",
        "knowledge_files",
        "shop_configs",
        "shops",
    ):
        try:
            op.drop_table(table_name)
        except Exception:
            pass
