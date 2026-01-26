"""Database connection and session management.

Engine and session factory are created lazily to avoid import-time side effects.
This allows tests to override DATABASE_URL before any connections are made.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


# Module-level state - initialized lazily
_engine: Optional[AsyncEngine] = None
_async_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def get_engine() -> AsyncEngine:
    """Get or create the async database engine.

    Engine is created on first access, not at import time.
    This allows tests to set DATABASE_URL before initialization.
    """
    global _engine
    if _engine is None:
        from app.core.config import get_settings
        settings = get_settings()

        _engine = create_async_engine(
            settings.database_url,
            echo=settings.debug,
            pool_pre_ping=True,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session factory.

    Session factory is created on first access.
    """
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_db_context() -> AsyncGenerator[AsyncSession, None]:
    """Context manager for database sessions outside of FastAPI dependencies."""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Verify database connection.

    Note: Schema creation/migration is handled by Alembic.
    Run 'alembic upgrade head' before starting the app.
    """
    from sqlalchemy import text
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Close database connections."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


def reset_engine() -> None:
    """Reset engine state. For testing only."""
    global _engine, _async_session_factory
    _engine = None
    _async_session_factory = None
