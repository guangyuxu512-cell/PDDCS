"""给 shop_configs 加 auto_restart / force_online 字段的迁移脚本。"""

from __future__ import annotations

from backend.db.database import get_db


def migrate() -> None:
    """为已有数据库补充运行策略字段。"""
    with get_db() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(shop_configs)").fetchall()}
        if "auto_restart" not in columns:
            conn.execute("ALTER TABLE shop_configs ADD COLUMN auto_restart INTEGER NOT NULL DEFAULT 0")
        if "force_online" not in columns:
            conn.execute("ALTER TABLE shop_configs ADD COLUMN force_online INTEGER NOT NULL DEFAULT 0")


if __name__ == "__main__":
    migrate()
    print("Migration complete: auto_restart, force_online added to shop_configs")
