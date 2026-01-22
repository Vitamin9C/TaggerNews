"""Story repository for database operations."""

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from taggernews.domain.story import Story
from taggernews.infrastructure.models import StoryModel, SummaryModel, TagModel


class StoryRepository:
    """Repository for Story CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def get_by_id(self, story_id: int) -> StoryModel | None:
        """Get a story by its ID."""
        stmt = (
            select(StoryModel)
            .options(selectinload(StoryModel.summary), selectinload(StoryModel.tags))
            .where(StoryModel.id == story_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_hn_id(self, hn_id: int) -> StoryModel | None:
        """Get a story by its HN ID."""
        stmt = select(StoryModel).where(StoryModel.hn_id == hn_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_stories(
        self,
        offset: int = 0,
        limit: int = 30,
    ) -> list[StoryModel]:
        """List stories with pagination, ordered by score."""
        stmt = (
            select(StoryModel)
            .options(selectinload(StoryModel.summary), selectinload(StoryModel.tags))
            .order_by(StoryModel.score.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_stories_by_tag(
        self,
        tag_name: str,
        offset: int = 0,
        limit: int = 30,
    ) -> list[StoryModel]:
        """List stories filtered by tag name."""
        stmt = (
            select(StoryModel)
            .join(StoryModel.tags)
            .where(TagModel.name == tag_name)
            .options(selectinload(StoryModel.summary), selectinload(StoryModel.tags))
            .order_by(StoryModel.score.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_tag(self, tag_name: str) -> int:
        """Count stories with a specific tag."""
        from sqlalchemy import func

        stmt = (
            select(func.count(StoryModel.id)).join(StoryModel.tags).where(TagModel.name == tag_name)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def count(self) -> int:
        """Get total story count."""
        from sqlalchemy import func

        stmt = select(func.count(StoryModel.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_date_range(self) -> tuple[datetime | None, datetime | None]:
        """Get the date range of stories in the database.

        Returns:
            Tuple of (oldest_date, newest_date) or (None, None) if no stories
        """
        from sqlalchemy import func

        stmt = select(
            func.min(StoryModel.hn_created_at),
            func.max(StoryModel.hn_created_at),
        )
        result = await self.session.execute(stmt)
        row = result.one()
        return row[0], row[1]

    async def list_stories_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        tag_name: str | None = None,
        offset: int = 0,
        limit: int = 30,
    ) -> list[StoryModel]:
        """List stories within a date range, optionally filtered by tag."""
        stmt = (
            select(StoryModel)
            .options(
                selectinload(StoryModel.summary),
                selectinload(StoryModel.tags),
            )
            .where(StoryModel.hn_created_at >= start_date)
            .where(StoryModel.hn_created_at <= end_date)
        )

        if tag_name:
            stmt = stmt.join(StoryModel.tags).where(TagModel.name == tag_name)

        stmt = stmt.order_by(StoryModel.score.desc()).offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_date_range(
        self,
        start_date: datetime,
        end_date: datetime,
        tag_name: str | None = None,
    ) -> int:
        """Count stories within a date range, optionally filtered by tag."""
        from sqlalchemy import func

        stmt = (
            select(func.count(StoryModel.id))
            .where(StoryModel.hn_created_at >= start_date)
            .where(StoryModel.hn_created_at <= end_date)
        )

        if tag_name:
            stmt = stmt.join(StoryModel.tags).where(TagModel.name == tag_name)

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    def get_today_range(self) -> tuple[datetime, datetime]:
        """Get today's date range (midnight to now)."""
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now

    def get_this_week_range(self) -> tuple[datetime, datetime]:
        """Get this week's date range (Monday midnight to now)."""
        now = datetime.now()
        days_since_monday = now.weekday()
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return start, now

    async def upsert(self, story: Story) -> StoryModel:
        """Insert or update a story.

        If story with same hn_id exists, update it. Otherwise, create new.
        """
        existing = await self.get_by_hn_id(story.hn_id)

        if existing:
            # Update existing story
            existing.title = story.title
            existing.url = story.url
            existing.score = story.score
            existing.author = story.author
            existing.comment_count = story.comment_count
            await self.session.flush()
            return existing
        else:
            # Create new story
            model = StoryModel(
                hn_id=story.hn_id,
                title=story.title,
                url=story.url,
                score=story.score,
                author=story.author,
                comment_count=story.comment_count,
                hn_created_at=story.hn_created_at,
            )
            self.session.add(model)
            await self.session.flush()
            return model

    async def upsert_many(self, stories: list[Story]) -> list[StoryModel]:
        """Upsert multiple stories."""
        models = []
        for story in stories:
            model = await self.upsert(story)
            models.append(model)
        return models


class SummaryRepository:
    """Repository for Summary CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def get_by_story_id(self, story_id: int) -> SummaryModel | None:
        """Get summary for a story."""
        stmt = select(SummaryModel).where(SummaryModel.story_id == story_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        story_id: int,
        text: str,
        model: str,
    ) -> SummaryModel:
        """Create a new summary."""
        summary = SummaryModel(
            story_id=story_id,
            text=text,
            model=model,
        )
        self.session.add(summary)
        await self.session.flush()
        return summary

    async def get_stories_without_summary(self, limit: int = 10) -> list[StoryModel]:
        """Get stories that don't have summaries yet."""
        stmt = (
            select(StoryModel)
            .outerjoin(SummaryModel)
            .where(SummaryModel.id.is_(None))
            .order_by(StoryModel.score.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class TagRepository:
    """Repository for Tag CRUD operations."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def get_or_create(
        self,
        name: str,
        slug: str | None = None,
        level: int = 3,
        is_misc: bool = True,
    ) -> TagModel:
        """Get an existing tag or create a new one."""
        from taggernews.services.tag_taxonomy import normalize_slug

        tag_slug = slug or normalize_slug(name)
        stmt = select(TagModel).where(TagModel.slug == tag_slug)
        result = await self.session.execute(stmt)
        tag = result.scalar_one_or_none()

        if not tag:
            tag = TagModel(
                name=name,
                slug=tag_slug,
                level=level,
                is_misc=is_misc,
                usage_count=1,
            )
            self.session.add(tag)
            await self.session.flush()

        return tag

    async def get_all_tags(self) -> list[TagModel]:
        """Get all tags ordered by level and usage."""
        stmt = select(TagModel).order_by(TagModel.level, TagModel.usage_count.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_tags_grouped_by_level(self) -> dict[int, list[dict]]:
        """Get tags grouped by level with story counts.

        Returns:
            {1: [{"name": "Tech", "slug": "tech", "count": 50}, ...],
             2: [...], 3: [...]}
        """
        from sqlalchemy import func

        from taggernews.infrastructure.models import story_tags

        stmt = (
            select(
                TagModel.name,
                TagModel.slug,
                TagModel.level,
                func.count(story_tags.c.story_id).label("count"),
            )
            .outerjoin(story_tags, TagModel.id == story_tags.c.tag_id)
            .group_by(TagModel.id, TagModel.name, TagModel.slug, TagModel.level)
            .order_by(TagModel.level, func.count(story_tags.c.story_id).desc())
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        grouped: dict[int, list[dict]] = {1: [], 2: [], 3: []}
        for name, slug, level, count in rows:
            level_key = min(level, 3)  # Group 3+ together
            grouped[level_key].append(
                {
                    "name": name,
                    "slug": slug,
                    "count": count,
                }
            )

        return grouped

    async def get_tags_with_counts(self) -> list[tuple[str, int, int]]:
        """Get all tags with their story counts and levels."""
        from sqlalchemy import func

        from taggernews.infrastructure.models import story_tags

        stmt = (
            select(
                TagModel.name,
                func.count(story_tags.c.story_id),
                TagModel.level,
            )
            .outerjoin(story_tags, TagModel.id == story_tags.c.tag_id)
            .group_by(TagModel.id, TagModel.name, TagModel.level)
            .order_by(TagModel.level, func.count(story_tags.c.story_id).desc())
        )
        result = await self.session.execute(stmt)
        return list(result.all())
