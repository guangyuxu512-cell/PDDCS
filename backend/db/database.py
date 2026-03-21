from __future__ import annotations

import asyncio
import os
import sqlite3
import threading
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from backend.core.crypto import ensure_encryption_key


DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "pddcs.db"
ALEMBIC_INI_PATH = Path(__file__).resolve().parents[2] / "alembic.ini"

_SYNC_DRIVER_MAP: dict[str, str] = {
    "sqlite+aiosqlite": "sqlite",
    "mysql+aiomysql": "mysql+pymysql",
    "postgresql+asyncpg": "postgresql+psycopg",
}


@dataclass(slots=True)
class _EngineState:
    database_url: str
    sync_database_url: str
    async_engine: AsyncEngine
    sync_engine: Engine
    async_session_factory: async_sessionmaker[AsyncSession]
    sync_session_factory: sessionmaker[Session]


_ENGINE_LOCK = threading.Lock()
_ENGINE_STATE: _EngineState | None = None


def _sqlite_url_from_path(path: Path) -> str:
    normalized = path.as_posix()
    if normalized.startswith("/"):
        return f"sqlite+aiosqlite://{normalized}"
    return f"sqlite+aiosqlite:///{normalized}"


def get_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        return database_url
    return _sqlite_url_from_path(DB_PATH)


def _to_sync_database_url(database_url: str) -> str:
    url = make_url(database_url)
    drivername = _SYNC_DRIVER_MAP.get(url.drivername, url.drivername)
    return str(url.set(drivername=drivername))


def get_sync_database_url() -> str:
    return _to_sync_database_url(get_database_url())


def _sqlite_path_from_url(database_url: str) -> Path:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite"):
        raise RuntimeError("Legacy sqlite compatibility is only available for sqlite databases")
    if url.database in (None, "", ":memory:"):
        return Path(":memory:")
    return Path(url.database)


def _ensure_sqlite_directory(database_url: str) -> None:
    try:
        db_path = _sqlite_path_from_url(database_url)
    except RuntimeError:
        return

    if db_path == Path(":memory:"):
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)


def _set_sqlite_pragmas(dbapi_connection: Any, _: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    cursor.close()


def _dispose_state(state: _EngineState) -> None:
    state.sync_engine.dispose()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(state.async_engine.dispose())
        return
    loop.create_task(state.async_engine.dispose())


def _build_engine_state(database_url: str) -> _EngineState:
    sync_database_url = _to_sync_database_url(database_url)
    _ensure_sqlite_directory(database_url)

    async_engine = create_async_engine(
        database_url,
        future=True,
        poolclass=NullPool,
    )
    sync_engine = create_engine(
        sync_database_url,
        future=True,
        poolclass=NullPool,
    )

    url = make_url(database_url)
    if url.drivername.startswith("sqlite"):
        event.listen(async_engine.sync_engine, "connect", _set_sqlite_pragmas)
        event.listen(sync_engine, "connect", _set_sqlite_pragmas)

    return _EngineState(
        database_url=database_url,
        sync_database_url=sync_database_url,
        async_engine=async_engine,
        sync_engine=sync_engine,
        async_session_factory=async_sessionmaker(async_engine, expire_on_commit=False),
        sync_session_factory=sessionmaker(sync_engine, expire_on_commit=False),
    )


def _get_engine_state() -> _EngineState:
    global _ENGINE_STATE

    database_url = get_database_url()
    sync_database_url = _to_sync_database_url(database_url)

    with _ENGINE_LOCK:
        if (
            _ENGINE_STATE is not None
            and _ENGINE_STATE.database_url == database_url
            and _ENGINE_STATE.sync_database_url == sync_database_url
        ):
            return _ENGINE_STATE

        old_state = _ENGINE_STATE
        _ENGINE_STATE = _build_engine_state(database_url)

    if old_state is not None:
        _dispose_state(old_state)

    return _ENGINE_STATE


def get_sync_engine() -> Engine:
    return _get_engine_state().sync_engine


def get_async_engine() -> AsyncEngine:
    return _get_engine_state().async_engine


@contextmanager
def get_sync_session() -> Iterator[Session]:
    session = _get_engine_state().sync_session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    session = _get_engine_state().async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


def get_connection() -> sqlite3.Connection:
    database_url = get_database_url()
    db_path = _sqlite_path_from_url(database_url)
    if db_path == Path(":memory:"):
        target = ":memory:"
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        target = str(db_path)

    conn = sqlite3.connect(target, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except sqlite3.DatabaseError:
        pass
    return conn


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _alembic_config() -> Config:
    config = Config(str(ALEMBIC_INI_PATH))
    config.set_main_option("sqlalchemy.url", get_sync_database_url())
    return config


def init_database() -> None:
    ensure_encryption_key()
    _ensure_sqlite_directory(get_database_url())
    command.upgrade(_alembic_config(), "head")
