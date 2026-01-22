"""HTMX-powered web views."""

from datetime import datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from taggernews.api.dependencies import StoryRepoDep, TagRepoDep

router = APIRouter(tags=["web"])

# Templates configuration
templates = Jinja2Templates(directory="templates")


def parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string in YYYY-MM-DD format."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return None


async def get_filtered_stories(
    story_repo: StoryRepoDep,
    period: str | None,
    date_from: str | None,
    date_to: str | None,
    tag: str | None,
    offset: int,
    limit: int,
) -> tuple[list, int]:
    """Get stories with combined date and tag filtering."""
    start_date = None
    end_date = None

    # Determine date range based on period
    if period == "today":
        start_date, end_date = story_repo.get_today_range()
    elif period == "week":
        start_date, end_date = story_repo.get_this_week_range()
    elif period == "custom":
        start_date = parse_date(date_from)
        end_date = parse_date(date_to)
        if end_date:
            # End of day for end_date
            end_date = end_date.replace(hour=23, minute=59, second=59)

    # Get stories based on filters
    if start_date and end_date:
        stories = await story_repo.list_stories_by_date_range(
            start_date, end_date, tag_name=tag, offset=offset, limit=limit
        )
        total = await story_repo.count_by_date_range(start_date, end_date, tag_name=tag)
    elif tag:
        stories = await story_repo.list_stories_by_tag(tag, offset, limit)
        total = await story_repo.count_by_tag(tag)
    else:
        stories = await story_repo.list_stories(offset, limit)
        total = await story_repo.count()

    return stories, total


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    story_repo: StoryRepoDep,
    tag_repo: TagRepoDep,
    tag: str | None = None,
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
) -> HTMLResponse:
    """Render the main page with stories and tags sidebar."""
    stories, total = await get_filtered_stories(
        story_repo, period, date_from, date_to, tag, offset=0, limit=30
    )

    # Get flat tags grouped by level for sidebar
    tags_by_level = await tag_repo.get_tags_grouped_by_level()

    # Get date range of stories in DB
    oldest_date, newest_date = await story_repo.get_date_range()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "stories": stories,
            "total": total,
            "offset": 0,
            "limit": 30,
            "tags_by_level": tags_by_level,
            "active_tag": tag,
            "active_period": period or "all",
            "date_from": date_from,
            "date_to": date_to,
            "db_oldest_date": oldest_date,
            "db_newest_date": newest_date,
        },
    )


@router.get("/stories/more", response_class=HTMLResponse)
async def load_more_stories(
    request: Request,
    story_repo: StoryRepoDep,
    offset: int = 0,
    limit: int = 30,
    tag: str | None = None,
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
) -> HTMLResponse:
    """HTMX endpoint for infinite scroll."""
    stories, total = await get_filtered_stories(
        story_repo, period, date_from, date_to, tag, offset, limit
    )
    has_more = offset + len(stories) < total

    return templates.TemplateResponse(
        request=request,
        name="partials/story_list.html",
        context={
            "stories": stories,
            "offset": offset + limit,
            "limit": limit,
            "has_more": has_more,
            "active_tag": tag,
            "active_period": period or "all",
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@router.get("/stories/filter", response_class=HTMLResponse)
async def filter_stories(
    request: Request,
    story_repo: StoryRepoDep,
    tag: str | None = None,
    period: str | None = None,
    date_from: str | None = Query(None, alias="from"),
    date_to: str | None = Query(None, alias="to"),
) -> HTMLResponse:
    """HTMX endpoint for filtering - returns story list partial."""
    stories, total = await get_filtered_stories(
        story_repo, period, date_from, date_to, tag, offset=0, limit=30
    )
    has_more = len(stories) < total

    return templates.TemplateResponse(
        request=request,
        name="partials/story_list.html",
        context={
            "stories": stories,
            "offset": 30,
            "limit": 30,
            "has_more": has_more,
            "active_tag": tag,
            "active_period": period or "all",
            "date_from": date_from,
            "date_to": date_to,
        },
    )
