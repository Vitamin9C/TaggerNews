"""Scraper service - orchestrates fetching and storing stories."""

import logging
import time

from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.config import get_settings
from taggernews.infrastructure.csv_logger import get_scraping_logger
from taggernews.infrastructure.hn_client import HNClient
from taggernews.repositories.story_repo import (
    StoryRepository,
    SummaryRepository,
    TagRepository,
)
from taggernews.services.summarizer import SummarizerService

logger = logging.getLogger(__name__)
settings = get_settings()
csv_logger = get_scraping_logger()


class ScraperService:
    """Service for scraping HN stories and generating summaries."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize scraper with database session."""
        self.session = session
        self.hn_client = HNClient()
        self.story_repo = StoryRepository(session)
        self.summary_repo = SummaryRepository(session)
        self.tag_repo = TagRepository(session)
        self.summarizer = SummarizerService()

    async def scrape_top_stories(self, limit: int | None = None) -> int:
        """Scrape stories from HN (top + new) and store in database.

        Args:
            limit: Maximum stories to fetch (defaults to config)

        Returns:
            Number of stories processed
        """
        limit = limit or settings.top_stories_count
        start_time = time.perf_counter()

        try:
            # Fetch story IDs from both top and new
            fetch_start = time.perf_counter()
            story_ids = await self.hn_client.get_all_story_ids(limit=limit)
            if not story_ids:
                logger.warning("No story IDs fetched")
                return 0

            # Fetch stories concurrently
            stories = await self.hn_client.get_stories(story_ids)
            fetch_duration_ms = (time.perf_counter() - fetch_start) * 1000
            csv_logger.log("fetch_stories", fetch_duration_ms, len(stories))

            if not stories:
                logger.warning("No stories fetched")
                return 0

            # Upsert to database
            upsert_start = time.perf_counter()
            models = await self.story_repo.upsert_many(stories)
            upsert_duration_ms = (time.perf_counter() - upsert_start) * 1000
            csv_logger.log("upsert_stories", upsert_duration_ms, len(models))
            logger.info(f"Upserted {len(models)} stories")

            return len(models)

        finally:
            await self.hn_client.close()
            total_duration_ms = (time.perf_counter() - start_time) * 1000
            csv_logger.log("scrape_top_stories_total", total_duration_ms, limit)

    async def generate_missing_summaries(self, limit: int = 10) -> int:
        """Generate summaries for stories that don't have them.

        Args:
            limit: Maximum stories to summarize

        Returns:
            Number of summaries generated
        """
        import asyncio

        from taggernews.services.tag_taxonomy import TaxonomyService

        start_time = time.perf_counter()

        # Get stories without summaries
        stories_without = await self.summary_repo.get_stories_without_summary(
            limit=limit
        )

        if not stories_without:
            logger.info("All stories have summaries")
            return 0

        # Convert models to domain objects
        from taggernews.domain.story import Story

        stories = [
            Story(
                id=story_model.id,
                hn_id=story_model.hn_id,
                title=story_model.title,
                url=story_model.url,
                score=story_model.score,
                author=story_model.author,
                comment_count=story_model.comment_count,
                hn_created_at=story_model.hn_created_at,
            )
            for story_model in stories_without
        ]

        # Initialize taxonomy service
        taxonomy_service = TaxonomyService(self.session)

        # Process concurrently with semaphore to limit parallelism
        semaphore = asyncio.Semaphore(settings.summarization_batch_size)

        async def process_story(story: Story) -> bool:
            async with semaphore:
                story_start = time.perf_counter()
                result = await self.summarizer.summarize_story(story)
                if result:
                    summary, flat_tags = result
                    await self.summary_repo.create(
                        story_id=story.id or 0,
                        text=summary.text,
                        model=summary.model,
                    )
                    # Resolve flat tags using TaxonomyService
                    story_model = await self.story_repo.get_by_id(story.id or 0)
                    if story_model:
                        tag_models = await taxonomy_service.resolve_tags(flat_tags)
                        for tag in tag_models:
                            if tag not in story_model.tags:
                                story_model.tags.append(tag)
                        # Mark story as processed
                        story_model.is_summarized = True
                        story_model.is_tagged = True
                        logger.debug(f"Story {story.hn_id}: {len(tag_models)} tags")
                    story_duration_ms = (time.perf_counter() - story_start) * 1000
                    csv_logger.log(
                        "summarize_story", story_duration_ms, 1, len(summary.text)
                    )
                    return True
                return False

        results = await asyncio.gather(*[process_story(s) for s in stories])
        count = sum(results)

        total_duration_ms = (time.perf_counter() - start_time) * 1000
        csv_logger.log("generate_missing_summaries_total", total_duration_ms, count)

        logger.info(f"Generated {count} summaries")
        return count
