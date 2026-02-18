"""Story API endpoints."""

from fastapi import APIRouter, HTTPException, Query

from taggernews.api.dependencies import ApiKeyDep, ScraperDep, StoryRepoDep
from taggernews.api.v1.schemas import ScrapeResponse, StoryListResponse, StoryResponse

router = APIRouter(prefix="/stories", tags=["stories"])


@router.get("", response_model=StoryListResponse)
async def list_stories(
    story_repo: StoryRepoDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
) -> StoryListResponse:
    """List stories with pagination, ordered by score."""

    stories = await story_repo.list_stories(offset=offset, limit=limit)
    total = await story_repo.count()

    return StoryListResponse(
        stories=[StoryResponse.model_validate(s) for s in stories],
        total=total,
        offset=offset,
        limit=limit,
        has_more=offset + len(stories) < total,
    )


@router.get("/{story_id}", response_model=StoryResponse)
async def get_story(
    story_id: int,
    story_repo: StoryRepoDep,
) -> StoryResponse:
    """Get a single story by ID."""
    story = await story_repo.get_by_id(story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")
    return StoryResponse.model_validate(story)


@router.post("/refresh", response_model=ScrapeResponse)
async def refresh_stories(
    scraper: ScraperDep,
    _auth: ApiKeyDep,
) -> ScrapeResponse:
    """Manually trigger story refresh from HN API."""
    stories_count = await scraper.scrape_top_stories()
    summaries_count = await scraper.generate_missing_summaries()

    return ScrapeResponse(
        message="Refresh completed successfully",
        stories_processed=stories_count,
        summaries_generated=summaries_count,
    )
