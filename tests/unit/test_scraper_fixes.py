
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from taggernews.repositories.scraper_state_repo import ScraperStateRepository
from taggernews.services.scraper import ScraperService
from taggernews.infrastructure.hn_client import HNClient
from taggernews.infrastructure.models import ScraperStateModel, StoryModel

class TestScraperFixes:
    """Tests for recent code quality fixes."""

    @pytest.mark.asyncio
    async def test_race_condition_lock_acquisition(self):
        """Verify that get_or_create_state_with_lock acquires advisory lock."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)
        
        # Mock get_state to return None (simulation: state doesn't exist)
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
        
        # 3. Verify datetime.now(timezone.utc) usage
        added_state = mock_session.add.call_args[0][0]
        assert added_state.last_run_at.tzinfo == timezone.utc

    @pytest.mark.asyncio
    async def test_race_condition_existing_state(self):
        """Verify lock acquisition when state already exists."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        repo = ScraperStateRepository(mock_session)
        
        existing_state = ScraperStateModel(id=1, state_type="continuous", current_item_id=50)
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
    async def test_chunking_large_id_list(self):
        """Verify get_existing_hn_ids chunks large lists."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        # Mock execute result for iteration
        mock_result = MagicMock()
        mock_result.all.return_value = [] # Return empty for simplicity
        mock_session.execute.return_value = mock_result
        
        repo = ScraperStateRepository(mock_session)
        
        # Create list larger than 1000 (chunk size)
        large_list = list(range(2500)) 
        
        # Act
        await repo.get_existing_hn_ids(large_list)
        
        # Assert
        # Should be called 3 times: 0-1000, 1000-2000, 2000-2500
        assert mock_session.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_no_chunking_small_id_list(self):
        """Verify get_existing_hn_ids does not chunk small lists."""
        # Arrange
        mock_session = AsyncMock(spec=AsyncSession)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute.return_value = mock_result
        
        repo = ScraperStateRepository(mock_session)
        
        small_list = list(range(500))
        
        # Act
        await repo.get_existing_hn_ids(small_list)
        
        # Assert
        assert mock_session.execute.call_count == 1

    @pytest.mark.asyncio
    async def test_hn_client_get_max_item_id_success(self):
        """Test successful fetch of max item ID."""
        client = HNClient()
        # Mock _fetch_with_retry
        client._fetch_with_retry = AsyncMock(return_value=123456)
        
        result = await client.get_max_item_id()
        assert result == 123456

    @pytest.mark.asyncio
    async def test_hn_client_get_max_item_id_none(self):
        """Test failure (None return) from max item ID fetch."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=None)
        
        # Should return None and log error (we verify return value)
        result = await client.get_max_item_id()
        assert result is None

    @pytest.mark.asyncio
    async def test_hn_client_get_max_item_id_invalid_type(self):
        """Test unexpected type from max item ID fetch."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value="not an int")
        
        # Should return None and log warning
        result = await client.get_max_item_id()
        assert result is None
