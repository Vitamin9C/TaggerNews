"""FastAPI dependency injection providers."""

import secrets
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.agents.orchestrator import AgentOrchestrator, get_orchestrator
from taggernews.config import get_settings
from taggernews.infrastructure.database import get_session
from taggernews.repositories.agent_repo import AgentRepository
from taggernews.repositories.story_repo import (
    StoryRepository,
    SummaryRepository,
    TagRepository,
)
from taggernews.services.scraper import ScraperService

# Type alias for database session dependency
SessionDep = Annotated[AsyncSession, Depends(get_session)]

# --- API Key Authentication ---

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Verify API key for write endpoints.

    If API_KEY is not configured (empty), auth is skipped (dev mode).
    In production, set API_KEY env var to enforce authentication.
    """
    settings = get_settings()
    if not settings.api_key:
        return "anonymous"
    if not api_key or not secrets.compare_digest(api_key, settings.api_key):
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return api_key


ApiKeyDep = Annotated[str, Depends(require_api_key)]


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


async def get_agent_repository(
    session: SessionDep,
) -> AsyncGenerator[AgentRepository, None]:
    """Provide AgentRepository instance."""
    yield AgentRepository(session)


def get_agent_orchestrator() -> AgentOrchestrator:
    """Provide AgentOrchestrator instance."""
    return get_orchestrator()


# Type aliases for commonly used dependencies
StoryRepoDep = Annotated[StoryRepository, Depends(get_story_repository)]
SummaryRepoDep = Annotated[SummaryRepository, Depends(get_summary_repository)]
TagRepoDep = Annotated[TagRepository, Depends(get_tag_repository)]
ScraperDep = Annotated[ScraperService, Depends(get_scraper_service)]
AgentRepoDep = Annotated[AgentRepository, Depends(get_agent_repository)]
OrchestratorDep = Annotated[AgentOrchestrator, Depends(get_agent_orchestrator)]
