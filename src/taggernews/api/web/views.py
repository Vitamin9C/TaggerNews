"""HTMX-powered web views."""

import json
from datetime import UTC, datetime

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from taggernews.api.dependencies import StoryRepoDep, TagRepoDep
from taggernews.repositories.story_repo import TagFilter

router = APIRouter(tags=["web"])

# Templates configuration
templates = Jinja2Templates(directory="templates")


def parse_date(date_str: str | None) -> datetime | None:
    """Parse a date string in YYYY-MM-DD format."""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
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


def _parse_json_list(s: str | None) -> list[str]:
    """Parse a JSON-encoded list of strings from query parameter."""
    if not s:
        return []
    try:
        result = json.loads(s)
        if not isinstance(result, list):
            return []
        return [item for item in result if isinstance(item, str)]
    except json.JSONDecodeError:
        return []


@router.get("/api/stories/advanced-filter", response_class=HTMLResponse)
async def advanced_filter_stories(
    request: Request,
    story_repo: StoryRepoDep,
    l1_include: str | None = Query(None, description="JSON array of L1 tags to include"),
    l1_exclude: str | None = Query(None, description="JSON array of L1 tags to exclude"),
    l2_include: str | None = Query(None, description="JSON array of L2 tags to include"),
    l2_exclude: str | None = Query(None, description="JSON array of L2 tags to exclude"),
    l3_include: str | None = Query(None, description="JSON array of L3 tags to include"),
    offset: int = 0,
    limit: int = 30,
) -> HTMLResponse:
    """HTMX endpoint for advanced tag filtering.

    Query parameters accept JSON-encoded arrays:
    - l1_include: ["Tech", "Business"]
    - l2_include: ["AI/ML", "Web"]
    - l2_exclude: ["Finance"]

    Returns HTML partial for HTMX swapping.
    """
    tag_filter = TagFilter(
        l1_include=_parse_json_list(l1_include),
        l1_exclude=_parse_json_list(l1_exclude),
        l2_include=_parse_json_list(l2_include),
        l2_exclude=_parse_json_list(l2_exclude),
        l3_include=_parse_json_list(l3_include),
    )

    stories = await story_repo.list_stories_by_tag_filter(tag_filter, offset, limit)
    total = await story_repo.count_by_tag_filter(tag_filter)
    has_more = offset + len(stories) < total

    return templates.TemplateResponse(
        request=request,
        name="partials/story_list.html",
        context={
            "stories": stories,
            "offset": offset + limit,
            "limit": limit,
            "has_more": has_more,
            "active_tag": None,
            "active_period": "all",
            "date_from": None,
            "date_to": None,
        },
    )


@router.get("/api/stories/advanced-filter.json")
async def advanced_filter_stories_json(
    story_repo: StoryRepoDep,
    l1_include: str | None = Query(None, description="JSON array of L1 tags to include"),
    l1_exclude: str | None = Query(None, description="JSON array of L1 tags to exclude"),
    l2_include: str | None = Query(None, description="JSON array of L2 tags to include"),
    l2_exclude: str | None = Query(None, description="JSON array of L2 tags to exclude"),
    l3_include: str | None = Query(None, description="JSON array of L3 tags to include"),
    offset: int = 0,
    limit: int = 30,
) -> JSONResponse:
    """JSON API endpoint for advanced tag filtering.

    Query parameters accept JSON-encoded arrays:
    - l1_include: ["Tech", "Business"]
    - l2_include: ["AI/ML", "Web"]
    - l2_exclude: ["Finance"]
    """
    tag_filter = TagFilter(
        l1_include=_parse_json_list(l1_include),
        l1_exclude=_parse_json_list(l1_exclude),
        l2_include=_parse_json_list(l2_include),
        l2_exclude=_parse_json_list(l2_exclude),
        l3_include=_parse_json_list(l3_include),
    )

    stories = await story_repo.list_stories_by_tag_filter(tag_filter, offset, limit)
    total = await story_repo.count_by_tag_filter(tag_filter)

    return JSONResponse({
        "stories": [
            {
                "id": s.id,
                "hn_id": s.hn_id,
                "title": s.title,
                "url": s.url,
                "score": s.score,
                "author": s.author,
                "comment_count": s.comment_count,
                "summary": s.summary.text if s.summary else None,
                "tags": [{"name": t.name, "level": t.level} for t in s.tags],
            }
            for s in stories
        ],
        "total": total,
        "offset": offset,
        "limit": limit,
        "has_more": offset + len(stories) < total,
    })


@router.get("/api/tags/grouped")
async def get_grouped_tags(tag_repo: TagRepoDep) -> JSONResponse:
    """Get tags grouped for filter UI.

    Returns:
        JSON with l1, l2, l3 tag arrays and categories grouped by mother category.
    """
    by_level = await tag_repo.get_tags_grouped_by_level()
    by_category = await tag_repo.get_tags_grouped_by_category()

    return JSONResponse({
        "l1": by_level.get(1, []),
        "l2": by_level.get(2, []),
        "l3": by_level.get(3, []),
        "categories": by_category,
    })
