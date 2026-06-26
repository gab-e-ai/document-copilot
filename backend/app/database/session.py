from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


def _get_async_database_url(url: str) -> str:
    """Convert sync database URL to async URL for use with create_async_engine."""
    # Replace psycopg:// with psycopg_async://
    if url.startswith("postgresql+psycopg://"):
        return url.replace("postgresql+psycopg://", "postgresql+psycopg_async://", 1)
    return url


_engine = create_async_engine(
    _get_async_database_url(settings.database_url),
    pool_pre_ping=True,
)
AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    _engine, expire_on_commit=False
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Async session factory for FastAPI dependency injection."""
    async with AsyncSessionLocal() as session:
        yield session
