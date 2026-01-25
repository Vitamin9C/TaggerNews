"""Dev-only API endpoints for testing tag extension."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from taggernews.api.dependencies import TagRepoDep
from taggernews.config import get_settings
from taggernews.infrastructure.database import async_session_factory
from taggernews.services.scraper import ScraperService

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/dev", tags=["dev"])


class CreateTagRequest(BaseModel):
    """Request to create a new tag."""

    name: str
    level: int = 2  # Default to L2 topic


class TagResponse(BaseModel):
    """Tag response."""

    id: int
    name: str
    slug: str
    level: int


@router.post("/tags", response_model=TagResponse)
async def create_tag(
    request: CreateTagRequest,
    tag_repo: TagRepoDep,
) -> TagResponse:
    """Manually create a tag for testing. Dev mode only."""
    if settings.is_production:
        raise HTTPException(403, "Not available in production")

    if not settings.enable_manual_tag_extension:
        raise HTTPException(
            403, "Manual tag extension disabled. Set ENABLE_MANUAL_TAG_EXTENSION=true in .env"
        )

    # Validate level
    if request.level not in (2, 3):
        raise HTTPException(400, "Level must be 2 (topic) or 3 (specific)")

    tag = await tag_repo.get_or_create(
        name=request.name,
        level=request.level,
        is_misc=(request.level == 3),
    )

    logger.info(f"Created L{request.level} tag: {request.name}")

    return TagResponse(
        id=tag.id,
        name=tag.name,
        slug=tag.slug,
        level=tag.level,
    )


@router.get("/tags")
async def list_tags(tag_repo: TagRepoDep) -> dict:
    """List all tags grouped by level. Dev mode only."""
    if settings.is_production:
        raise HTTPException(403, "Not available in production")

    return await tag_repo.get_tags_grouped_by_level()


class ScrapeResponse(BaseModel):
    """Response for scrape trigger."""

    message: str
    stories_scraped: int
    summaries_generated: int


async def _run_scrape(days: int) -> tuple[int, int]:
    """Run the scrape job for N days of history."""
    async with async_session_factory() as session:
        scraper = ScraperService(session)

        # Calculate limit based on days
        limit = min(500, settings.top_stories_count * days)
        stories_count = await scraper.scrape_top_stories(limit=limit)

        # Generate summaries for all stories without them
        total_summaries = 0
        while True:
            count = await scraper.generate_missing_summaries(
                limit=settings.summarization_batch_size
            )
            if count == 0:
                break
            total_summaries += count
            await session.commit()

        await session.commit()
        return stories_count, total_summaries


@router.post("/scrape", response_model=ScrapeResponse)
async def trigger_scrape(days: int = 1) -> ScrapeResponse:
    """Trigger scraping for past N days (dev-only).

    Args:
        days: Number of days of history to scrape (default: 1)

    Returns:
        Status message with counts
    """
    if settings.is_production:
        raise HTTPException(403, "Not available in production")

    if days < 1 or days > 30:
        raise HTTPException(400, "Days must be between 1 and 30")

    logger.info(f"Dev scrape triggered for {days} day(s)")

    # Run synchronously for simplicity (could be background task)
    stories_count, summaries_count = await _run_scrape(days)

    return ScrapeResponse(
        message=f"Scrape completed for {days} day(s)",
        stories_scraped=stories_count,
        summaries_generated=summaries_count,
    )
