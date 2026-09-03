"""Async SQLAlchemy engine + session factory.

Provides a singleton async engine configured with explicit connection pooling
(read/write pool) and a request-scoped ``async_sessionmaker`` for dependency
injection by FastAPI routers.

Exposed:

* ``engine``                -> global :class:`AsyncEngine`
* ``AsyncSessionLocal``     -> configured :class:`async_sessionmaker`
* ``get_db_session``        -> async generator used by FastAPI dependencies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def build_engine() -> AsyncEngine:
    """Create and return a configured :class:`AsyncEngine`.

    Connection pooling is sized from ``settings``. Because Nakshatra is read
    heavy (hazard scans, map tiles) but bursty during scenario computation, we
    keep a moderately large pool with overflow to avoid queueing the analytics
    reads behind a small pool.
    """
    return create_async_engine(
        settings.postgres_async_url_resolved,
        echo=settings.DB_ECHO,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_timeout=settings.DB_POOL_TIMEOUT,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_pre_ping=True,
        future=True,
    )


engine: AsyncEngine = build_engine()


AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """Yield a session for a request and guarantee release/rollback.

    A single transaction is implicitly wrapped by FastAPI dependency lifecycle;
    commit/rollback is delegated to the caller/request handler. We rely on
    ``autoflush=False`` so read-then-write patterns do not leak partial state.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def close_engine() -> None:
    """Dispose the engine (called at application shutdown)."""
    await engine.dispose()
