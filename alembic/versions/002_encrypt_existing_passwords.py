from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "002_encrypt_existing_passwords"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "shops" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("shops")}
    if "password" not in columns:
        return

    shops_table = sa.table(
        "shops",
        sa.column("id", sa.String()),
        sa.column("password", sa.Text()),
        sa.column("password_encrypted", sa.Text()),
        sa.column("password_hash", sa.Text()),
    )
    rows = bind.execute(
        sa.select(shops_table.c.id, shops_table.c.password).where(shops_table.c.password != "")
    ).all()
    if not rows:
        return

    from backend.core.crypto import encrypt, hash_password

    for row in rows:
        bind.execute(
            shops_table.update()
            .where(shops_table.c.id == row.id)
            .values(
                password="",
                password_encrypted=encrypt(str(row.password)),
                password_hash=hash_password(str(row.password)),
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "shops" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("shops")}
    if "password_encrypted" not in columns and "password_hash" not in columns:
        return

    shops_table = sa.table(
        "shops",
        sa.column("id", sa.String()),
        sa.column("password_encrypted", sa.Text()),
        sa.column("password_hash", sa.Text()),
    )
    bind.execute(shops_table.update().values(password_encrypted="", password_hash=""))
