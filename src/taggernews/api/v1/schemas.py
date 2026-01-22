"""Pydantic schemas for API request/response models."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SummaryResponse(BaseModel):
    """Response schema for story summary."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    model: str
    created_at: datetime


class StoryResponse(BaseModel):
    """Response schema for a story."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    hn_id: int
    title: str
    url: str | None
    score: int
    author: str
    comment_count: int
    hn_created_at: datetime
    created_at: datetime
    summary: SummaryResponse | None = None


class StoryListResponse(BaseModel):
    """Response schema for paginated story list."""

    stories: list[StoryResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


class ScrapeResponse(BaseModel):
    """Response schema for scrape operation."""

    message: str
    stories_processed: int
    summaries_generated: int
