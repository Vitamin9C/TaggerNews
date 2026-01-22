"""FastAPI dependency injection providers."""

from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.infrastructure.database import get_session
from taggernews.repositories.story_repo import (
    StoryRepository,
    SummaryRepository,
    TagRepository,
)
from taggernews.services.scraper import ScraperService

# Type alias for database session dependency
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_story_repository(
    session: SessionDep,
) -> AsyncGenerator[StoryRepository, None]:
    """Provide StoryRepository instance."""
    yield StoryRepository(session)


async def get_summary_repository(
    session: SessionDep,
) -> AsyncGenerator[SummaryRepository, None]:
    """Provide SummaryRepository instance."""
    yield SummaryRepository(session)


async def get_scraper_service(
    session: SessionDep,
) -> AsyncGenerator[ScraperService, None]:
    """Provide ScraperService instance."""
    yield ScraperService(session)


async def get_tag_repository(
    session: SessionDep,
) -> AsyncGenerator[TagRepository, None]:
    """Provide TagRepository instance."""
    yield TagRepository(session)


# Type aliases for commonly used dependencies
StoryRepoDep = Annotated[StoryRepository, Depends(get_story_repository)]
SummaryRepoDep = Annotated[SummaryRepository, Depends(get_summary_repository)]
TagRepoDep = Annotated[TagRepository, Depends(get_tag_repository)]
ScraperDep = Annotated[ScraperService, Depends(get_scraper_service)]
