from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "pddcs.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


def _init_db(conn: sqlite3.Connection) -> None:
    """首次运行时执行 schema.sql 建表。"""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def get_connection() -> sqlite3.Connection:
    """获取一个 SQLite 连接。"""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    """上下文管理器：自动 commit / rollback / close。"""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database() -> None:
    """应用启动时调用一次，确保表已建好。"""
    with get_db() as conn:
        _init_db(conn)
