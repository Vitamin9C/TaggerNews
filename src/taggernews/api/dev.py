"""Dev-only API endpoints for testing tag extension."""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from taggernews.api.dependencies import TagRepoDep
from taggernews.config import get_settings

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
