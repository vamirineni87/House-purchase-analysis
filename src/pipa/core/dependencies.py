"""FastAPI dependency injection providers."""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from pipa.core.config import AppConfig, load_config
from pipa.core.database import create_engine, create_session_factory

# Module-level singletons (initialized on first call)
_config: AppConfig | None = None
_engine = None
_session_factory = None


def get_config() -> AppConfig:
    """Get or create application config."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_engine():
    """Get or create database engine."""
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_engine(config.database_url)
    return _engine


def get_session_factory():
    """Get or create session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = create_session_factory(get_engine())
    return _session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def reset_singletons():
    """Reset module-level singletons (for testing)."""
    global _config, _engine, _session_factory
    _config = None
    _engine = None
    _session_factory = None
