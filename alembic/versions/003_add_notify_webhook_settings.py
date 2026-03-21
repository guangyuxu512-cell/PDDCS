from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "003_add_notify_webhook_settings"
down_revision = "002_encrypt_existing_passwords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "system_settings" not in inspector.get_table_names():
        return

    settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String()),
        sa.column("value", sa.Text()),
        sa.column("updated_at", sa.Text()),
    )
    rows = bind.execute(
        sa.select(settings_table.c.key, settings_table.c.value)
    ).all()
    existing = {str(row.key): str(row.value or "") for row in rows}
    legacy_url = existing.get("alertWebhookUrl", "")
    notify_url = existing.get("notifyWebhookUrl", "")

    if "notifyWebhookUrl" not in existing:
        bind.execute(
            settings_table.insert().values(
                key="notifyWebhookUrl",
                value=notify_url or legacy_url,
                updated_at="",
            )
        )
    elif not notify_url and legacy_url:
        bind.execute(
            settings_table.update()
            .where(settings_table.c.key == "notifyWebhookUrl")
            .values(value=legacy_url)
        )

    if "notifyWebhookType" not in existing:
        bind.execute(
            settings_table.insert().values(
                key="notifyWebhookType",
                value="feishu",
                updated_at="",
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "system_settings" not in inspector.get_table_names():
        return

    settings_table = sa.table(
        "system_settings",
        sa.column("key", sa.String()),
    )
    bind.execute(
        settings_table.delete().where(
            settings_table.c.key.in_(("notifyWebhookUrl", "notifyWebhookType"))
        )
    )
