"""Background job scheduler for TaggerNews."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from taggernews.config import get_settings
from taggernews.infrastructure.database import async_session_factory
from taggernews.services.scraper import ScraperService

logger = logging.getLogger(__name__)
settings = get_settings()


class SchedulerService:
    """Manages background jobs for scraping and summarization."""

    def __init__(self) -> None:
        """Initialize the scheduler service."""
        self.scheduler = AsyncIOScheduler()
        self._startup_done = False

    async def _run_scrape_job(self) -> None:
        """Execute the scrape and summarize job."""
        logger.info("Starting scheduled scrape job...")
        try:
            async with async_session_factory() as session:
                scraper = ScraperService(session)
                stories_count = await scraper.scrape_top_stories()
                logger.info(f"Scraped {stories_count} stories")

                summaries_count = await scraper.generate_missing_summaries(
                    limit=settings.summarization_batch_size
                )
                logger.info(f"Generated {summaries_count} summaries")
                await session.commit()
        except Exception as e:
            logger.error(f"Scrape job failed: {e}")

    async def _run_recovery_job(self) -> None:
        """Process stories that failed tagging or summarization."""
        logger.info("Starting recovery job for unprocessed stories...")
        try:
            async with async_session_factory() as session:
                from taggernews.repositories.story_repo import StoryRepository

                story_repo = StoryRepository(session)
                scraper = ScraperService(session)

                # Get unprocessed stories
                unprocessed = await story_repo.get_unprocessed_stories(
                    limit=settings.summarization_batch_size
                )

                if not unprocessed:
                    logger.info("No unprocessed stories found")
                    return

                logger.info(f"Found {len(unprocessed)} unprocessed stories")

                # Process them through the summarization pipeline
                count = await scraper.generate_missing_summaries(
                    limit=len(unprocessed)
                )
                await session.commit()
                logger.info(f"Recovery job: processed {count} stories")
        except Exception as e:
            logger.error(f"Recovery job failed: {e}")

    async def _run_startup_backfill(self) -> None:
        """Backfill stories from the past N days on startup."""
        if self._startup_done:
            return

        days = settings.startup_backfill_days
        logger.info(f"Starting startup backfill for past {days} days...")

        try:
            async with async_session_factory() as session:
                scraper = ScraperService(session)

                # Scrape more stories on startup for backfill
                stories_count = await scraper.scrape_top_stories(
                    limit=min(500, settings.top_stories_count * days)
                )
                logger.info(f"Backfill: scraped {stories_count} stories")

                # Generate summaries in batches
                total_summaries = 0
                while True:
                    count = await scraper.generate_missing_summaries(
                        limit=settings.summarization_batch_size
                    )
                    if count == 0:
                        break
                    total_summaries += count
                    await session.commit()
                    logger.info(f"Backfill progress: {total_summaries} summaries")

                logger.info(f"Backfill complete: {total_summaries} total summaries")
                self._startup_done = True
        except Exception as e:
            logger.error(f"Startup backfill failed: {e}")

    def start(self) -> None:
        """Start the scheduler with configured jobs."""
        # Add hourly scrape job
        self.scheduler.add_job(
            self._run_scrape_job,
            trigger=IntervalTrigger(hours=settings.scrape_interval_hours),
            id="hourly_scrape",
            name="Hourly Scrape and Summarize",
            replace_existing=True,
        )
        logger.info(
            f"Scheduled hourly scrape (every {settings.scrape_interval_hours}h)"
        )

        # Add recovery job for failed processing
        self.scheduler.add_job(
            self._run_recovery_job,
            trigger=IntervalTrigger(minutes=settings.recovery_interval_minutes),
            id="recovery_job",
            name="Recovery Job for Unprocessed Stories",
            replace_existing=True,
        )
        logger.info(
            f"Scheduled recovery job (every {settings.recovery_interval_minutes}m)"
        )

        # Add startup backfill job (runs once at startup)
        self.scheduler.add_job(
            self._run_startup_backfill,
            trigger=None,  # Run immediately
            id="startup_backfill",
            name="Startup Backfill",
            replace_existing=True,
        )
        logger.info(
            f"Scheduled startup backfill ({settings.startup_backfill_days} days)"
        )

        self.scheduler.start()
        logger.info("Scheduler started")

    def shutdown(self) -> None:
        """Shutdown the scheduler gracefully."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Scheduler shut down")


# Singleton instance
_scheduler_service: SchedulerService | None = None


def get_scheduler() -> SchedulerService:
    """Get or create the scheduler service singleton."""
    global _scheduler_service
    if _scheduler_service is None:
        _scheduler_service = SchedulerService()
    return _scheduler_service
