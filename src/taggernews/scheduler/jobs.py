"""Background job scheduler for TaggerNews."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from taggernews.agents.orchestrator import get_orchestrator
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
        self._backfill_complete = False

    async def _run_backfill_job(self) -> None:
        """Run backfill scraping (chunked for resumability).

        This job runs every few minutes until backfill is complete.
        Progress is tracked in scraper_state table.
        """
        if self._backfill_complete:
            return

        logger.info("Running backfill job...")
        try:
            async with async_session_factory() as session:
                scraper = ScraperService(session)
                result = await scraper.run_backfill(
                    days=settings.scraper_backfill_days,
                    batch_size=settings.scraper_backfill_batch_size,
                    max_batches=settings.scraper_backfill_max_batches,
                )

                if result.get("status") == "already_completed":
                    self._backfill_complete = True
                    logger.info("Backfill already complete")
                elif result.get("status") == "completed":
                    self._backfill_complete = True
                    scanned = result.get("items_scanned", 0)
                    new_stories = result.get("stories_new", 0)
                    logger.info(
                        f"Backfill completed: {scanned} scanned, "
                        f"{new_stories} new stories"
                    )
                else:
                    scanned = result.get("items_scanned", 0)
                    new_stories = result.get("stories_new", 0)
                    logger.info(
                        f"Backfill progress: {scanned} scanned, "
                        f"{new_stories} new stories"
                    )

        except Exception as e:
            logger.error(f"Backfill job failed: {e}", exc_info=True)

    async def _run_continuous_scrape_job(self) -> None:
        """Run continuous scraping for new stories.

        Polls for new items and fetches from curated lists.
        """
        logger.info("Running continuous scrape job...")
        try:
            async with async_session_factory() as session:
                scraper = ScraperService(session)
                result = await scraper.run_continuous_scrape(
                    batch_size=settings.scraper_continuous_batch_size,
                )

                if result.get("error"):
                    logger.error(f"Continuous scrape error: {result['error']}")
                else:
                    gap = result.get("gap_items", 0)
                    scanned = result.get("items_scanned", 0)
                    new = result.get("stories_new", 0)
                    curated = result.get("curated_new", 0)
                    logger.info(
                        f"Continuous scrape: gap={gap}, scanned={scanned}, "
                        f"new={new}, curated={curated}"
                    )

                # Also generate summaries for new stories
                summaries_count = await scraper.generate_missing_summaries(
                    limit=settings.summarization_batch_size
                )
                if summaries_count > 0:
                    logger.info(f"Generated {summaries_count} summaries")
                await session.commit()

        except Exception as e:
            logger.error(f"Continuous scrape job failed: {e}", exc_info=True)

    async def _run_scrape_job(self) -> None:
        """Execute legacy scrape job (for compatibility).

        Note: This is kept for compatibility. The enhanced scraper
        system (backfill + continuous) is recommended for production.
        """
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

    async def _run_weekly_agent_analysis(self) -> None:
        """Weekly agent analysis job for tag taxonomy management."""
        logger.info("Starting weekly agent analysis...")
        try:
            orchestrator = get_orchestrator()
            mode = "auto-apply" if settings.agent_enable_auto_approve else "proposal"
            result = await orchestrator.run_analysis_pipeline(mode=mode)
            logger.info(
                f"Agent analysis complete: {result['proposals_created']} proposals, "
                f"{result.get('auto_approved', 0)} auto-approved"
            )
        except Exception as e:
            logger.error(f"Agent analysis failed: {e}", exc_info=True)

    def start(self) -> None:
        """Start the scheduler with configured jobs."""
        # Enhanced backfill job - runs every N minutes until complete
        backfill_interval = settings.scraper_backfill_interval_minutes
        self.scheduler.add_job(
            self._run_backfill_job,
            trigger=IntervalTrigger(minutes=backfill_interval),
            id="enhanced_backfill",
            name="Enhanced Backfill Scraping",
            replace_existing=True,
        )
        logger.info(
            f"Scheduled backfill job (every {backfill_interval}m, "
            f"{settings.scraper_backfill_days} days)"
        )

        # Enhanced continuous scrape job - runs every N minutes
        continuous_interval = settings.scraper_continuous_interval_minutes
        self.scheduler.add_job(
            self._run_continuous_scrape_job,
            trigger=IntervalTrigger(minutes=continuous_interval),
            id="continuous_scrape",
            name="Continuous Scraping",
            replace_existing=True,
        )
        logger.info(f"Scheduled continuous scrape (every {continuous_interval}m)")

        # Recovery job for failed processing
        recovery_interval = settings.recovery_interval_minutes
        self.scheduler.add_job(
            self._run_recovery_job,
            trigger=IntervalTrigger(minutes=recovery_interval),
            id="recovery_job",
            name="Recovery Job for Unprocessed Stories",
            replace_existing=True,
        )
        logger.info(f"Scheduled recovery job (every {recovery_interval}m)")

        # Weekly agent analysis job
        agent_interval = settings.agent_run_interval_weeks
        self.scheduler.add_job(
            self._run_weekly_agent_analysis,
            trigger=IntervalTrigger(weeks=agent_interval),
            id="weekly_agent_analysis",
            name="Weekly Tag Taxonomy Analysis",
            replace_existing=True,
        )
        logger.info(f"Scheduled weekly agent analysis (every {agent_interval} week(s))")

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
