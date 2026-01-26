"""Database connection and session management."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


def _create_engine():
    """Create async engine with appropriate settings for the database type."""
    database_url = settings.database_url

    # Base engine options
    engine_options = {
        "echo": settings.debug,
    }

    # SQLite doesn't support connection pool options
    if not database_url.startswith("sqlite"):
        engine_options.update({
            "pool_pre_ping": True,
            "pool_size": 10,
            "max_overflow": 20,
        })

    return create_async_engine(database_url, **engine_options)


# Create async engine
engine = _create_engine()

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for getting async database session."""
    async with async_session_factory() as session:
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
    async with async_session_factory() as session:
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
    async with engine.begin() as conn:
        # Just verify the connection works
        await conn.execute(text("SELECT 1"))


async def close_db() -> None:
    """Close database connections."""
    await engine.dispose()
