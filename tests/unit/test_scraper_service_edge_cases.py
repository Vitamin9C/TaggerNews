"""Edge case tests for ScraperService: backfill, continuous, and batch processing."""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.domain.story import Story
from taggernews.infrastructure.models import ScraperStateModel
from taggernews.services.scraper import ScraperService


class TestScrapeTopStories:
    """Tests for scrape_top_stories edge cases."""

    @pytest.mark.asyncio
    async def test_no_story_ids_returns_zero(self, caplog):
        """Returns 0 when no story IDs are fetched."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)
        service.hn_client.get_all_story_ids = AsyncMock(return_value=[])
        service.hn_client.close = AsyncMock()

        with caplog.at_level(logging.WARNING):
            result = await service.scrape_top_stories()

        assert result == 0
        assert "No story IDs fetched" in caplog.text

    @pytest.mark.asyncio
    async def test_no_stories_fetched_returns_zero(self, caplog):
        """Returns 0 when story IDs exist but fetch yields no stories."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)
        service.hn_client.get_all_story_ids = AsyncMock(return_value=[1, 2, 3])
        service.hn_client.get_stories = AsyncMock(return_value=[])
        service.hn_client.close = AsyncMock()

        with caplog.at_level(logging.WARNING):
            result = await service.scrape_top_stories()

        assert result == 0
        assert "No stories fetched" in caplog.text

    @pytest.mark.asyncio
    async def test_always_closes_hn_client(self):
        """HN client is always closed even if an error occurs."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)
        service.hn_client.get_all_story_ids = AsyncMock(
            side_effect=Exception("network error")
        )
        service.hn_client.close = AsyncMock()

        with pytest.raises(Exception, match="network error"):
            await service.scrape_top_stories()

        service.hn_client.close.assert_called_once()


class TestRunBackfill:
    """Tests for run_backfill edge cases."""

    @pytest.mark.asyncio
    async def test_already_completed_returns_early(self):
        """Returns immediately when backfill already completed."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        mock_state = ScraperStateModel(
            id=1, state_type="backfill", current_item_id=100, status="completed"
        )
        service.state_repo.get_state = AsyncMock(return_value=mock_state)
        service.hn_client.close = AsyncMock()

        result = await service.run_backfill(days=7)

        assert result["status"] == "already_completed"

    @pytest.mark.asyncio
    async def test_resumes_from_existing_active_state(self, caplog):
        """Resumes from existing active state instead of starting fresh."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        mock_state = ScraperStateModel(
            id=1,
            state_type="backfill",
            current_item_id=500,
            status="active",
            items_processed=100,
            stories_found=10,
        )
        service.state_repo.get_state = AsyncMock(return_value=mock_state)
        service.state_repo.create_or_update_state = AsyncMock(return_value=mock_state)
        service.state_repo.increment_counters = AsyncMock()
        service.hn_client.close = AsyncMock()

        # Process one batch then stop
        service._process_item_batch = AsyncMock(return_value={
            "items_scanned": 100,
            "stories_found": 5,
            "stories_new": 3,
            "reached_target_date": True,
        })

        with caplog.at_level(logging.INFO):
            result = await service.run_backfill(days=7, batch_size=100, max_batches=1)

        assert "Resuming backfill" in caplog.text
        assert result["stories_new"] == 3

    @pytest.mark.asyncio
    async def test_max_item_id_failure_returns_error(self):
        """Returns error when HN max_item_id cannot be fetched."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)
        service.state_repo.get_state = AsyncMock(return_value=None)
        service.hn_client.get_max_item_id = AsyncMock(return_value=None)
        service.hn_client.close = AsyncMock()

        result = await service.run_backfill(days=7)

        assert "error" in result

    @pytest.mark.asyncio
    async def test_max_batches_limit_stops_processing(self):
        """Stops processing when max_batches limit is reached."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.state_repo.get_state = AsyncMock(return_value=None)
        service.hn_client.get_max_item_id = AsyncMock(return_value=10000)
        service.hn_client.close = AsyncMock()

        mock_state = ScraperStateModel(
            id=1, state_type="backfill", current_item_id=10000, status="active",
            items_processed=0, stories_found=0,
        )
        service.state_repo.create_or_update_state = AsyncMock(return_value=mock_state)
        service.state_repo.increment_counters = AsyncMock()

        service._process_item_batch = AsyncMock(return_value={
            "items_scanned": 100,
            "stories_found": 5,
            "stories_new": 3,
            "reached_target_date": False,
        })

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.run_backfill(days=30, batch_size=100, max_batches=2)

        assert result["batches_processed"] == 2
        assert result["status"] == "in_progress"


class TestRunContinuousScrape:
    """Tests for run_continuous_scrape edge cases."""

    @pytest.mark.asyncio
    async def test_no_gap_only_curated(self):
        """When current_item_id equals max_item, only curated lists are fetched."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.hn_client.get_max_item_id = AsyncMock(return_value=50000)
        service.hn_client.close = AsyncMock()

        mock_state = ScraperStateModel(
            id=1, state_type="continuous", current_item_id=50000,
            items_processed=0, stories_found=0,
        )
        service.state_repo.get_or_create_state_with_lock = AsyncMock(
            return_value=(mock_state, False)
        )
        service._update_from_curated_lists = AsyncMock(return_value=5)

        result = await service.run_continuous_scrape()

        assert result["gap_items"] == 0
        assert result["items_scanned"] == 0
        assert result["curated_new"] == 5

    @pytest.mark.asyncio
    async def test_max_item_failure_returns_error(self):
        """Returns error when max_item cannot be fetched."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)
        service.hn_client.get_max_item_id = AsyncMock(return_value=None)
        service.hn_client.close = AsyncMock()

        result = await service.run_continuous_scrape()

        assert "error" in result

    @pytest.mark.asyncio
    async def test_always_closes_client_on_error(self):
        """Client is closed even when processing raises."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)
        service.hn_client.get_max_item_id = AsyncMock(
            side_effect=Exception("connection failed")
        )
        service.hn_client.close = AsyncMock()

        with pytest.raises(Exception, match="connection failed"):
            await service.run_continuous_scrape()

        service.hn_client.close.assert_called_once()


class TestProcessItemBatch:
    """Tests for _process_item_batch edge cases."""

    @pytest.mark.asyncio
    async def test_all_items_already_exist(self):
        """Returns zero new stories when all items already in DB."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        # All IDs already exist
        service.state_repo.get_existing_hn_ids = AsyncMock(
            return_value={1, 2, 3, 4, 5}
        )

        result = await service._process_item_batch([1, 2, 3, 4, 5])

        assert result["items_scanned"] == 5
        assert result["stories_new"] == 0

    @pytest.mark.asyncio
    async def test_filters_stories_before_target_timestamp(self):
        """Filters out stories older than target_timestamp during backfill."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.state_repo.get_existing_hn_ids = AsyncMock(return_value=set())

        # Create stories: one before target, one after
        target = datetime(2026, 1, 15, tzinfo=UTC)
        old_story = Story(
            id=None, hn_id=1, title="Old", url=None, score=10,
            author="a", comment_count=0,
            hn_created_at=datetime(2026, 1, 10, tzinfo=UTC),
        )
        new_story = Story(
            id=None, hn_id=2, title="New", url=None, score=20,
            author="b", comment_count=0,
            hn_created_at=datetime(2026, 1, 20, tzinfo=UTC),
        )

        service.hn_client.get_items_batch = AsyncMock(return_value=[old_story, new_story])
        service.story_repo.upsert_many = AsyncMock(return_value=[MagicMock()])

        result = await service._process_item_batch([1, 2], target_timestamp=target)

        assert result["reached_target_date"] is True
        # upsert_many should only get the new story
        call_args = service.story_repo.upsert_many.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0].hn_id == 2

    @pytest.mark.asyncio
    async def test_no_stories_in_batch(self):
        """Handles batch where no items are stories."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.state_repo.get_existing_hn_ids = AsyncMock(return_value=set())
        service.hn_client.get_items_batch = AsyncMock(return_value=[])

        result = await service._process_item_batch([1, 2, 3])

        assert result["stories_found"] == 0
        assert result["stories_new"] == 0

    @pytest.mark.asyncio
    async def test_empty_batch(self):
        """Handles empty batch of item IDs."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.state_repo.get_existing_hn_ids = AsyncMock(return_value=set())
        service.hn_client.get_items_batch = AsyncMock(return_value=[])

        result = await service._process_item_batch([])

        assert result["items_scanned"] == 0


class TestUpdateFromCuratedLists:
    """Tests for _update_from_curated_lists."""

    @pytest.mark.asyncio
    async def test_all_stories_already_exist(self):
        """Returns 0 when all curated stories already in DB."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.hn_client.get_top_story_ids = AsyncMock(return_value=[1, 2])
        service.hn_client.get_new_story_ids = AsyncMock(return_value=[2, 3])
        service.hn_client.get_best_story_ids = AsyncMock(return_value=[1, 3])

        # All exist
        service.state_repo.get_existing_hn_ids = AsyncMock(return_value={1, 2, 3})

        result = await service._update_from_curated_lists()
        assert result == 0

    @pytest.mark.asyncio
    async def test_new_stories_from_curated_lists(self):
        """Returns count of new stories added from curated lists."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.hn_client.get_top_story_ids = AsyncMock(return_value=[1, 2])
        service.hn_client.get_new_story_ids = AsyncMock(return_value=[3])
        service.hn_client.get_best_story_ids = AsyncMock(return_value=[4])

        service.state_repo.get_existing_hn_ids = AsyncMock(return_value={1})

        mock_stories = [MagicMock(), MagicMock()]
        service.hn_client.get_items_batch = AsyncMock(return_value=mock_stories)
        service.story_repo.upsert_many = AsyncMock(return_value=mock_stories)

        result = await service._update_from_curated_lists()
        assert result == 2

    @pytest.mark.asyncio
    async def test_no_stories_fetched_from_curated(self):
        """Returns 0 when items_batch returns empty for curated IDs."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.hn_client.get_top_story_ids = AsyncMock(return_value=[1])
        service.hn_client.get_new_story_ids = AsyncMock(return_value=[])
        service.hn_client.get_best_story_ids = AsyncMock(return_value=[])
        service.state_repo.get_existing_hn_ids = AsyncMock(return_value=set())
        service.hn_client.get_items_batch = AsyncMock(return_value=[])

        result = await service._update_from_curated_lists()
        assert result == 0


class TestGetScrapingStatus:
    """Tests for get_scraping_status."""

    @pytest.mark.asyncio
    async def test_no_states_exist(self):
        """Returns default values when no scraper states exist."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.state_repo.get_state = AsyncMock(return_value=None)
        service.hn_client.get_max_item_id = AsyncMock(return_value=50000)
        service.state_repo.get_story_count = AsyncMock(return_value=0)

        status = await service.get_scraping_status()

        assert status["hn_max_item"] == 50000
        assert status["total_stories"] == 0
        assert status["backfill"]["status"] == "not_started"
        assert status["continuous"]["status"] == "not_started"
        assert status["continuous"]["gap"] == 0

    @pytest.mark.asyncio
    async def test_with_active_states(self):
        """Returns correct stats when states are active."""
        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        backfill_state = ScraperStateModel(
            id=1, state_type="backfill", current_item_id=40000,
            status="active", items_processed=5000, stories_found=200,
            last_run_at=datetime(2026, 1, 15, tzinfo=UTC),
        )
        continuous_state = ScraperStateModel(
            id=2, state_type="continuous", current_item_id=49000,
            status="active", items_processed=1000, stories_found=50,
            last_run_at=datetime(2026, 1, 15, 12, 0, tzinfo=UTC),
        )

        async def mock_get_state(state_type):
            if state_type == "backfill":
                return backfill_state
            return continuous_state

        service.state_repo.get_state = mock_get_state
        service.hn_client.get_max_item_id = AsyncMock(return_value=50000)
        service.state_repo.get_story_count = AsyncMock(return_value=250)

        status = await service.get_scraping_status()

        assert status["total_stories"] == 250
        assert status["backfill"]["status"] == "active"
        assert status["backfill"]["items_processed"] == 5000
        assert status["continuous"]["gap"] == 1000  # 50000 - 49000
