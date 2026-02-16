"""Scraper service - orchestrates fetching and storing stories."""

import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.config import get_settings
from taggernews.infrastructure.csv_logger import get_scraping_logger
from taggernews.infrastructure.hn_client import HNClient
from taggernews.repositories.scraper_state_repo import ScraperStateRepository
from taggernews.repositories.story_repo import (
    StoryRepository,
    SummaryRepository,
    TagRepository,
)
from taggernews.services.summarizer import SummarizerService

logger = logging.getLogger(__name__)
settings = get_settings()
csv_logger = get_scraping_logger()

# State type constants
STATE_BACKFILL = "backfill"
STATE_CONTINUOUS = "continuous"


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
        self.state_repo = ScraperStateRepository(session)

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

        Processes stories sequentially to avoid concurrent access to the
        shared SQLAlchemy session (AsyncSession is not task-safe).

        Args:
            limit: Maximum stories to summarize

        Returns:
            Number of summaries generated
        """
        from taggernews.domain.story import Story
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

        count = 0
        for story in stories:
            story_start = time.perf_counter()

            if story.id is None:
                logger.warning(f"Story {story.hn_id} has no database ID, skipping")
                continue

            result = await self.summarizer.summarize_story(story)
            if not result:
                continue

            summary, flat_tags = result
            await self.summary_repo.create(
                story_id=story.id,
                text=summary.text,
                model=summary.model,
            )
            # Resolve flat tags using TaxonomyService
            story_model = await self.story_repo.get_by_id(story.id)
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
            count += 1

        total_duration_ms = (time.perf_counter() - start_time) * 1000
        csv_logger.log("generate_missing_summaries_total", total_duration_ms, count)

        logger.info(f"Generated {count} summaries")
        return count

    # ========== ENHANCED SCRAPER METHODS ==========

    async def run_backfill(
        self,
        days: int,
        batch_size: int | None = None,
        max_batches: int | None = None,
    ) -> dict:
        """Run backfill scraping for past N days.

        Scans backwards from HN's max_item_id to cover historical stories.
        Progress is tracked in scraper_state table for resumability.

        Args:
            days: Number of days to backfill
            batch_size: Items per batch (defaults to config)
            max_batches: Max batches per run for chunked processing

        Returns:
            Dict with stats: {items_scanned, stories_found, stories_new, status}
        """
        batch_size = batch_size or settings.scraper_backfill_batch_size
        max_batches = max_batches or settings.scraper_backfill_max_batches
        target_timestamp = datetime.now(UTC) - timedelta(days=days)

        try:
            # Get or resume backfill state
            state = await self.state_repo.get_state(STATE_BACKFILL)

            if state and state.status == "completed":
                logger.info("Backfill already completed")
                return {"status": "already_completed"}

            if state and state.status == "active":
                # Resume from where we left off
                current_id = state.current_item_id
                logger.info(f"Resuming backfill from item {current_id}")
            else:
                # Start fresh from max_item
                max_item = await self.hn_client.get_max_item_id()
                if not max_item:
                    logger.error("Could not get max item ID from HN")
                    return {"error": "Could not get max item ID"}
                current_id = max_item
                state = await self.state_repo.create_or_update_state(
                    state_type=STATE_BACKFILL,
                    current_item_id=current_id,
                    target_timestamp=target_timestamp,
                    status="active",
                )
                logger.info(f"Starting backfill from item {current_id}")

            stats = {
                "items_scanned": 0,
                "stories_found": 0,
                "stories_new": 0,
                "batches_processed": 0,
                "status": "in_progress",
            }

            batches_done = 0
            reached_target = False

            while current_id > 0 and not reached_target:
                # Generate batch of item IDs (scanning backwards)
                batch_start = max(1, current_id - batch_size + 1)
                batch_ids = list(range(batch_start, current_id + 1))

                # Process batch
                batch_stats = await self._process_item_batch(
                    batch_ids, target_timestamp
                )

                stats["items_scanned"] += batch_stats["items_scanned"]
                stats["stories_found"] += batch_stats["stories_found"]
                stats["stories_new"] += batch_stats["stories_new"]
                stats["batches_processed"] += 1

                # Update state
                current_id = batch_start - 1
                await self.state_repo.create_or_update_state(
                    state_type=STATE_BACKFILL,
                    current_item_id=current_id,
                    target_timestamp=target_timestamp,
                    status="active",
                )
                await self.state_repo.increment_counters(
                    STATE_BACKFILL,
                    items_processed=batch_stats["items_scanned"],
                    stories_found=batch_stats["stories_new"],
                )
                await self.session.commit()

                logger.info(
                    f"Backfill batch {stats['batches_processed']}: "
                    f"scanned {batch_stats['items_scanned']}, "
                    f"found {batch_stats['stories_new']} new stories"
                )

                # Check if we've reached target date
                if batch_stats.get("reached_target_date"):
                    logger.info(f"Reached target date {target_timestamp}")
                    reached_target = True
                    break

                # Check max batches limit
                batches_done += 1
                if batches_done >= max_batches:
                    logger.info(f"Reached max batches limit ({max_batches})")
                    break

                # Brief pause to avoid rate limiting
                await asyncio.sleep(settings.scraper_rate_limit_delay_ms / 1000)

            # Mark as completed if we scanned everything
            if current_id <= 0 or reached_target:
                await self.state_repo.create_or_update_state(
                    state_type=STATE_BACKFILL,
                    current_item_id=current_id,
                    target_timestamp=target_timestamp,
                    status="completed",
                )
                await self.session.commit()
                stats["status"] = "completed"
                logger.info("Backfill completed")

            return stats

        finally:
            await self.hn_client.close()

    async def _process_item_batch(
        self,
        item_ids: list[int],
        target_timestamp: datetime | None = None,
    ) -> dict:
        """Process a batch of item IDs.

        1. Check which IDs already exist in DB (efficient batch lookup)
        2. Fetch only new items from HN
        3. Filter to stories only (not comments/jobs)
        4. Insert new stories

        Args:
            item_ids: List of HN item IDs to process
            target_timestamp: Optional cutoff for backfill

        Returns:
            Dict with batch stats
        """
        stats = {
            "items_scanned": len(item_ids),
            "stories_found": 0,
            "stories_new": 0,
            "reached_target_date": False,
        }

        # Check which items already exist (efficient DB lookup)
        existing_ids = await self.state_repo.get_existing_hn_ids(item_ids)
        new_ids = [iid for iid in item_ids if iid not in existing_ids]

        if not new_ids:
            logger.debug(f"All {len(item_ids)} items already exist")
            return stats

        # Fetch only new items from HN
        stories = await self.hn_client.get_items_batch(new_ids, filter_type="story")
        stats["stories_found"] = len(stories)

        # Check target timestamp if backfilling
        if target_timestamp and stories:
            # Check if oldest story in batch is before target
            oldest_story = min(stories, key=lambda s: s.hn_created_at)
            if oldest_story.hn_created_at < target_timestamp:
                # Filter out stories older than target
                stories = [
                    s for s in stories
                    if s.hn_created_at >= target_timestamp
                ]
                stats["reached_target_date"] = True

        # Insert new stories
        if stories:
            models = await self.story_repo.upsert_many(stories)
            stats["stories_new"] = len(models)

        return stats

    async def run_continuous_scrape(
        self,
        batch_size: int | None = None,
    ) -> dict:
        """Run continuous scraping for new stories.

        Polls forward from last processed item ID to catch new items.
        Also fetches from curated lists (top/new/best) for popular stories.

        Args:
            batch_size: Items per batch (defaults to config)

        Returns:
            Dict with stats
        """
        batch_size = batch_size or settings.scraper_continuous_batch_size

        try:
            # Get current max item from HN
            max_item = await self.hn_client.get_max_item_id()
            if not max_item:
                logger.error("Could not get max item ID")
                return {"error": "Could not get max item ID"}

            # Get or create state with advisory lock to prevent race conditions
            # If two jobs run simultaneously, only one will create the state
            state, was_created = (
                await self.state_repo.get_or_create_state_with_lock(
                    state_type=STATE_CONTINUOUS,
                    initial_item_id=max_item - 1,
                )
            )

            if was_created:
                logger.info(
                    f"Initialized continuous state at item {max_item - 1}"
                )

            last_processed = state.current_item_id

            gap = max_item - last_processed
            stats = {
                "items_scanned": 0,
                "stories_found": 0,
                "stories_new": 0,
                "gap_items": gap,
                "curated_new": 0,
            }

            # Process gap between last_processed and max_item
            if gap > 0:
                current_id = last_processed + 1
                while current_id <= max_item:
                    batch_end = min(current_id + batch_size - 1, max_item)
                    batch_ids = list(range(current_id, batch_end + 1))

                    batch_stats = await self._process_item_batch(batch_ids)

                    stats["items_scanned"] += batch_stats["items_scanned"]
                    stats["stories_found"] += batch_stats["stories_found"]
                    stats["stories_new"] += batch_stats["stories_new"]

                    current_id = batch_end + 1

                    # Update state periodically
                    await self.state_repo.create_or_update_state(
                        state_type=STATE_CONTINUOUS,
                        current_item_id=batch_end,
                        status="active",
                    )
                    await self.state_repo.increment_counters(
                        STATE_CONTINUOUS,
                        items_processed=batch_stats["items_scanned"],
                        stories_found=batch_stats["stories_new"],
                    )
                    await self.session.commit()

                    await asyncio.sleep(settings.scraper_rate_limit_delay_ms / 1000)

            # Also scrape from curated lists for popular stories
            curated_new = await self._update_from_curated_lists()
            stats["curated_new"] = curated_new

            logger.info(
                f"Continuous scrape: gap={gap}, scanned={stats['items_scanned']}, "
                f"new={stats['stories_new']}, curated_new={curated_new}"
            )

            return stats

        finally:
            await self.hn_client.close()

    async def _update_from_curated_lists(self) -> int:
        """Fetch stories from top/new/best lists for quick access to popular stories.

        This ensures we catch stories that become popular quickly,
        without waiting for the sequential ID scan.

        Returns:
            Number of new stories added from curated lists
        """
        # Get IDs from all lists
        top_ids = await self.hn_client.get_top_story_ids(limit=200)
        new_ids = await self.hn_client.get_new_story_ids(limit=200)
        best_ids = await self.hn_client.get_best_story_ids(limit=200)

        # Combine and deduplicate
        all_ids = list(set(top_ids + new_ids + best_ids))

        # Check which exist
        existing = await self.state_repo.get_existing_hn_ids(all_ids)
        new_story_ids = [sid for sid in all_ids if sid not in existing]

        if not new_story_ids:
            return 0

        stories = await self.hn_client.get_items_batch(
            new_story_ids, filter_type="story"
        )
        if stories:
            await self.story_repo.upsert_many(stories)
            logger.info(f"Added {len(stories)} stories from curated lists")
            return len(stories)

        return 0

    async def get_scraping_status(self) -> dict:
        """Get current scraping status and stats.

        Returns:
            Dict with backfill and continuous state info
        """
        backfill_state = await self.state_repo.get_state(STATE_BACKFILL)
        continuous_state = await self.state_repo.get_state(STATE_CONTINUOUS)

        max_item = await self.hn_client.get_max_item_id()
        story_count = await self.state_repo.get_story_count()

        backfill_last_run = None
        if backfill_state and backfill_state.last_run_at:
            backfill_last_run = backfill_state.last_run_at.isoformat()

        continuous_last_run = None
        if continuous_state and continuous_state.last_run_at:
            continuous_last_run = continuous_state.last_run_at.isoformat()

        continuous_gap = 0
        if continuous_state and max_item:
            continuous_gap = max_item - continuous_state.current_item_id

        return {
            "hn_max_item": max_item,
            "total_stories": story_count,
            "backfill": {
                "status": backfill_state.status if backfill_state else "not_started",
                "current_item": (
                    backfill_state.current_item_id if backfill_state else None
                ),
                "items_processed": (
                    backfill_state.items_processed if backfill_state else 0
                ),
                "stories_found": (
                    backfill_state.stories_found if backfill_state else 0
                ),
                "last_run": backfill_last_run,
            },
            "continuous": {
                "status": (
                    continuous_state.status if continuous_state else "not_started"
                ),
                "current_item": (
                    continuous_state.current_item_id if continuous_state else None
                ),
                "items_processed": (
                    continuous_state.items_processed if continuous_state else 0
                ),
                "stories_found": (
                    continuous_state.stories_found if continuous_state else 0
                ),
                "last_run": continuous_last_run,
                "gap": continuous_gap,
            },
        }
