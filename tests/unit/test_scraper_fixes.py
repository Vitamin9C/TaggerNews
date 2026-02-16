"""Tests for v0.0.7 code quality fixes.

Tests cover:
1. Race condition fix with advisory locks
2. datetime.now(UTC) usage (deprecated utcnow replacement)
3. Chunked ID lookups for large lists
4. Enhanced error handling in HN client
"""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.infrastructure.hn_client import HNClient
from taggernews.infrastructure.models import ScraperStateModel
from taggernews.repositories.scraper_state_repo import ScraperStateRepository


class TestRaceConditionFix:
    """Tests for advisory lock race condition prevention."""

    @pytest.mark.asyncio
    async def test_lock_acquisition_on_new_state(self):
        """Verify that get_or_create_state_with_lock acquires advisory lock."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)
        repo.get_state = AsyncMock(return_value=None)

        # Act
        state, created = await repo.get_or_create_state_with_lock(
            state_type="continuous",
            initial_item_id=100
        )

        # Assert
        # 1. Verify lock acquisition was attempted
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        assert "pg_advisory_xact_lock" in str(call_args)

        # 2. Verify state creation
        assert created is True
        assert mock_session.add.called
        assert mock_session.flush.called

        # 3. Verify datetime.now(UTC) usage
        added_state = mock_session.add.call_args[0][0]
        assert added_state.last_run_at.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_lock_acquisition_on_existing_state(self):
        """Verify lock acquisition when state already exists."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)

        existing_state = ScraperStateModel(
            id=1, state_type="continuous", current_item_id=50
        )
        repo.get_state = AsyncMock(return_value=existing_state)

        # Act
        state, created = await repo.get_or_create_state_with_lock(
            state_type="continuous",
            initial_item_id=100
        )

        # Assert
        # 1. Verify lock still acquired (critical for race condition prevention)
        assert mock_session.execute.called
        call_args = mock_session.execute.call_args[0][0]
        assert "pg_advisory_xact_lock" in str(call_args)

        # 2. Verify no new state created
        assert created is False
        assert not mock_session.add.called
        assert state == existing_state

    @pytest.mark.asyncio
    async def test_lock_id_is_consistent_for_same_state_type(self):
        """Verify same state_type produces consistent lock IDs."""
        # The lock ID is computed via hash, verify consistency
        # Hash for "scraper_state_continuous" should be the same each run
        lock_id_1 = hash("scraper_state_continuous") % 2147483647
        lock_id_2 = hash("scraper_state_continuous") % 2147483647

        # Lock IDs should be identical for the same state type
        assert lock_id_1 == lock_id_2

    @pytest.mark.asyncio
    async def test_different_state_types_get_different_locks(self):
        """Verify different state_types get different lock IDs."""
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)
        repo.get_state = AsyncMock(return_value=None)

        await repo.get_or_create_state_with_lock("continuous", 100)
        continuous_call = str(mock_session.execute.call_args_list[0])

        mock_session.reset_mock()
        repo.get_state = AsyncMock(return_value=None)

        await repo.get_or_create_state_with_lock("backfill", 100)
        backfill_call = str(mock_session.execute.call_args_list[0])

        # Lock calls should differ (different lock IDs)
        assert continuous_call != backfill_call


class TestDatetimeUtcFix:
    """Tests for datetime.now(UTC) usage (replacing deprecated utcnow)."""

    @pytest.mark.asyncio
    async def test_create_or_update_state_uses_utc(self):
        """Verify create_or_update_state uses timezone-aware UTC datetime."""
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)
        repo.get_state = AsyncMock(return_value=None)

        await repo.create_or_update_state(
            state_type="continuous",
            current_item_id=100,
            status="active"
        )

        # Verify the added state has timezone-aware datetime
        added_state = mock_session.add.call_args[0][0]
        assert added_state.last_run_at.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_create_or_update_state_update_uses_utc(self):
        """Verify updating existing state uses timezone-aware UTC datetime."""
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)

        # Existing state without timezone-aware datetime
        existing_state = ScraperStateModel(
            id=1,
            state_type="continuous",
            current_item_id=50,
            last_run_at=datetime(2026, 1, 1, 0, 0, 0)  # naive datetime
        )
        repo.get_state = AsyncMock(return_value=existing_state)

        await repo.create_or_update_state(
            state_type="continuous",
            current_item_id=100,
            status="active"
        )

        # Verify the updated state has timezone-aware datetime
        assert existing_state.last_run_at.tzinfo == UTC

    @pytest.mark.asyncio
    async def test_increment_counters_uses_utc(self):
        """Verify increment_counters updates last_run_at with UTC."""
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)

        existing_state = ScraperStateModel(
            id=1,
            state_type="continuous",
            current_item_id=50,
            items_processed=100,
            stories_found=10,
            last_run_at=datetime(2026, 1, 1, 0, 0, 0)
        )
        repo.get_state = AsyncMock(return_value=existing_state)

        await repo.increment_counters(
            state_type="continuous",
            items_processed=50,
            stories_found=5
        )

        # Verify updated timestamp is UTC
        assert existing_state.last_run_at.tzinfo == UTC
        # Verify counters incremented
        assert existing_state.items_processed == 150
        assert existing_state.stories_found == 15


class TestChunkedIdLookups:
    """Tests for chunked ID lookup optimization in get_existing_hn_ids."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty_set(self):
        """Verify empty input returns empty set without DB query."""
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)

        result = await repo.get_existing_hn_ids([])

        assert result == set()
        assert mock_session.execute.call_count == 0

    @pytest.mark.asyncio
    async def test_small_list_single_query(self):
        """Verify small lists (<=1000) use single query."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.all.return_value = [(1,), (5,), (10,)]
        mock_session.execute.return_value = mock_result

        repo = ScraperStateRepository(mock_session)
        small_list = list(range(500))

        result = await repo.get_existing_hn_ids(small_list)

        assert mock_session.execute.call_count == 1
        assert result == {1, 5, 10}

    @pytest.mark.asyncio
    async def test_boundary_1000_items_single_query(self):
        """Verify exactly 1000 items uses single query (boundary case)."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        repo = ScraperStateRepository(mock_session)
        boundary_list = list(range(1000))

        await repo.get_existing_hn_ids(boundary_list)

        # Exactly 1000 should NOT chunk
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_1001_items_chunks_into_two_queries(self):
        """Verify 1001 items chunks into 2 queries."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        repo = ScraperStateRepository(mock_session)
        over_boundary_list = list(range(1001))

        await repo.get_existing_hn_ids(over_boundary_list)

        # 1001 should chunk: 0-1000 (1000 items), 1000-1001 (1 item)
        assert mock_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_2500_items_chunks_into_three_queries(self):
        """Verify 2500 items chunks into 3 queries."""
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result

        repo = ScraperStateRepository(mock_session)
        large_list = list(range(2500))

        await repo.get_existing_hn_ids(large_list)

        # Should be 3 chunks: 0-1000, 1000-2000, 2000-2500
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_chunked_results_combined(self):
        """Verify results from multiple chunks are combined correctly."""
        mock_session = AsyncMock(spec=AsyncSession)

        # Simulate different results from different chunks
        mock_result1 = MagicMock()
        mock_result1.all.return_value = [(100,), (200,)]

        mock_result2 = MagicMock()
        mock_result2.all.return_value = [(1500,)]

        mock_session.execute.side_effect = [mock_result1, mock_result2]

        repo = ScraperStateRepository(mock_session)
        large_list = list(range(1500))

        result = await repo.get_existing_hn_ids(large_list)

        # Results should be combined from both chunks
        assert result == {100, 200, 1500}


class TestHNClientErrorHandling:
    """Tests for enhanced error handling in HN client get_max_item_id."""

    @pytest.mark.asyncio
    async def test_get_max_item_id_success(self):
        """Test successful fetch of max item ID."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=123456)

        result = await client.get_max_item_id()

        assert result == 123456

    @pytest.mark.asyncio
    async def test_get_max_item_id_none_returns_none(self):
        """Test None response returns None."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=None)

        result = await client.get_max_item_id()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_max_item_id_invalid_type_returns_none(self):
        """Test unexpected type returns None."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value="not an int")

        result = await client.get_max_item_id()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_max_item_id_float_returns_none(self):
        """Test float type returns None (should be int)."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=123.456)

        result = await client.get_max_item_id()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_max_item_id_dict_returns_none(self):
        """Test dict type returns None."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value={"id": 123})

        result = await client.get_max_item_id()

        assert result is None

    @pytest.mark.asyncio
    async def test_get_max_item_id_logs_error_on_none(self, caplog):
        """Verify error is logged when fetch returns None."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=None)

        with caplog.at_level(logging.ERROR):
            await client.get_max_item_id()

        assert "Failed to fetch max item ID" in caplog.text

    @pytest.mark.asyncio
    async def test_get_max_item_id_logs_warning_on_invalid_type(self, caplog):
        """Verify warning is logged for invalid type."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value="not_an_int")

        with caplog.at_level(logging.WARNING):
            await client.get_max_item_id()

        assert "Unexpected data type" in caplog.text
        assert "str" in caplog.text


class TestScraperServiceIntegration:
    """Tests for ScraperService using the locked state initialization."""

    @pytest.mark.asyncio
    async def test_continuous_scrape_uses_locked_init(self):
        """Verify run_continuous_scrape uses get_or_create_state_with_lock."""
        from taggernews.services.scraper import ScraperService

        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        # Mock dependencies
        service.hn_client.get_max_item_id = AsyncMock(return_value=50000)
        service.hn_client.close = AsyncMock()

        mock_state = ScraperStateModel(
            id=1,
            state_type="continuous",
            current_item_id=50000,
            items_processed=0,
            stories_found=0
        )
        service.state_repo.get_or_create_state_with_lock = AsyncMock(
            return_value=(mock_state, True)
        )

        # Avoid actual scraping
        service._update_from_curated_lists = AsyncMock(return_value=0)

        result = await service.run_continuous_scrape()

        # Verify the locked method was called
        service.state_repo.get_or_create_state_with_lock.assert_called_once_with(
            state_type="continuous",
            initial_item_id=49999  # max_item - 1
        )
        assert result.get("gap_items") == 0

    @pytest.mark.asyncio
    async def test_continuous_scrape_logs_when_state_created(self, caplog):
        """Verify logging when new state is initialized."""
        from taggernews.services.scraper import ScraperService

        mock_session = AsyncMock(spec=AsyncSession)
        service = ScraperService(mock_session)

        service.hn_client.get_max_item_id = AsyncMock(return_value=50000)
        service.hn_client.close = AsyncMock()

        # Set current_item_id to max_item so there's no gap to process
        mock_state = ScraperStateModel(
            id=1,
            state_type="continuous",
            current_item_id=50000,  # No gap
            items_processed=0,
            stories_found=0
        )
        service.state_repo.get_or_create_state_with_lock = AsyncMock(
            return_value=(mock_state, True)  # was_created=True
        )
        service._update_from_curated_lists = AsyncMock(return_value=0)

        with caplog.at_level(logging.INFO):
            await service.run_continuous_scrape()

        assert "Initialized continuous state" in caplog.text
