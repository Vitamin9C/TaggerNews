"""SQLAlchemy async database setup."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from taggernews.config import get_settings

settings = get_settings()

# Create async engine with connection pooling
engine = create_async_engine(
    settings.database_url,
    echo=not settings.is_production,
    pool_size=5,
    max_overflow=10,
)

# Session factory
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for FastAPI to get database session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
