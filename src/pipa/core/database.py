"""SQLAlchemy async engine and session factory for SQLite with WAL mode."""

from __future__ import annotations

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _set_sqlite_pragmas(dbapi_conn, connection_record):
    """Set SQLite pragmas for performance and reliability."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.close()


def create_engine(database_url: str):
    """Create async engine with SQLite-optimized settings."""
    engine = create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
    )

    # Set pragmas on every new connection
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragmas)

    return engine


def create_session_factory(engine) -> async_sessionmaker[AsyncSession]:
    """Create session factory bound to engine."""
    return async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def init_db(engine):
    """Initialize database — create tables from metadata if needed."""
    from pipa.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def healthcheck(engine) -> bool:
    """Verify database connectivity."""
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
