"""Edge case tests for HNClient: network failures, malformed data, rate limiting."""

import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from taggernews.infrastructure.hn_client import HNClient


def _make_mock_response(status=200, json_data=None):
    """Create a mock aiohttp response that works as async context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    return resp


def _make_mock_session(responses=None, side_effect=None):
    """Create a mock session whose .get() returns async context managers.

    Args:
        responses: List of mock response objects to return in order.
        side_effect: Exception or list of exceptions to raise from .get().
    """
    mock_session = MagicMock()
    mock_session.closed = False

    if side_effect is not None:
        # Wrap exceptions: .get() raises directly (before entering context)
        if isinstance(side_effect, list):
            effects = list(side_effect)
            call_idx = {"i": 0}

            @asynccontextmanager
            async def _get_raises(*args, **kwargs):
                idx = call_idx["i"]
                call_idx["i"] += 1
                effect = effects[idx]
                if isinstance(effect, Exception):
                    raise effect
                yield effect

            mock_session.get = MagicMock(side_effect=lambda *a, **kw: _get_raises(*a, **kw))
        else:
            @asynccontextmanager
            async def _get_raises_single(*args, **kwargs):
                raise side_effect

            mock_session.get = MagicMock(side_effect=lambda *a, **kw: _get_raises_single(*a, **kw))
    elif responses is not None:
        resp_list = list(responses)
        call_idx = {"i": 0}

        @asynccontextmanager
        async def _get_resp(*args, **kwargs):
            idx = call_idx["i"]
            call_idx["i"] += 1
            yield resp_list[idx]

        mock_session.get = MagicMock(side_effect=lambda *a, **kw: _get_resp(*a, **kw))
    return mock_session


class TestFetchWithRetry:
    """Tests for _fetch_with_retry error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_timeout_retries_up_to_max(self):
        """Verify TimeoutError triggers retries up to max_retries."""
        client = HNClient(base_url="http://fake", timeout_seconds=1)
        mock_session = _make_mock_session(
            side_effect=[TimeoutError(), TimeoutError(), TimeoutError()]
        )
        client._get_session = AsyncMock(return_value=mock_session)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._fetch_with_retry("http://fake/test", max_retries=3, base_delay=0)

        assert result is None
        assert mock_session.get.call_count == 3

    @pytest.mark.asyncio
    async def test_client_error_retries(self):
        """Verify aiohttp.ClientError triggers retries."""
        client = HNClient(base_url="http://fake", timeout_seconds=1)
        mock_session = _make_mock_session(
            side_effect=[
                aiohttp.ClientError("connection reset"),
                aiohttp.ClientError("connection reset"),
            ]
        )
        client._get_session = AsyncMock(return_value=mock_session)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._fetch_with_retry("http://fake/test", max_retries=2, base_delay=0)

        assert result is None
        assert mock_session.get.call_count == 2

    @pytest.mark.asyncio
    async def test_rate_limit_429_retries(self, caplog):
        """Verify 429 response triggers retry."""
        client = HNClient(base_url="http://fake")
        resp_429 = _make_mock_response(status=429)
        mock_session = _make_mock_session(responses=[resp_429, resp_429])
        client._get_session = AsyncMock(return_value=mock_session)

        with (
            patch("asyncio.sleep", new_callable=AsyncMock),
            caplog.at_level(logging.WARNING),
        ):
            result = await client._fetch_with_retry("http://fake/test", max_retries=2, base_delay=0.01)

        assert result is None
        assert "Rate limited" in caplog.text

    @pytest.mark.asyncio
    async def test_non_200_non_429_returns_none_immediately(self, caplog):
        """Verify non-200/429 status returns None without retry."""
        client = HNClient(base_url="http://fake")
        resp_500 = _make_mock_response(status=500)
        mock_session = _make_mock_session(responses=[resp_500])
        client._get_session = AsyncMock(return_value=mock_session)

        with caplog.at_level(logging.ERROR):
            result = await client._fetch_with_retry("http://fake/test", max_retries=3, base_delay=0)

        assert result is None
        assert "HTTP 500" in caplog.text
        assert mock_session.get.call_count == 1

    @pytest.mark.asyncio
    async def test_success_on_second_attempt(self):
        """Verify successful response after initial failure."""
        client = HNClient(base_url="http://fake")
        resp_ok = _make_mock_response(status=200, json_data={"id": 123})
        mock_session = _make_mock_session(
            side_effect=[TimeoutError(), resp_ok]
        )
        client._get_session = AsyncMock(return_value=mock_session)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await client._fetch_with_retry("http://fake/test", max_retries=3, base_delay=0)

        assert result == {"id": 123}
        assert mock_session.get.call_count == 2


class TestGetStory:
    """Tests for get_story edge cases."""

    @pytest.mark.asyncio
    async def test_returns_none_for_non_story_type(self):
        """get_story returns None for comments, jobs, polls."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value={"id": 1, "type": "comment"})

        result = await client.get_story(1)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_for_null_response(self):
        """get_story returns None when API returns null (deleted item)."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=None)

        result = await client.get_story(999999999)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_story_for_valid_data(self):
        """get_story returns Story for valid story data."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value={
            "id": 12345,
            "type": "story",
            "title": "Test",
            "time": 1700000000,
        })

        result = await client.get_story(12345)
        assert result is not None
        assert result.hn_id == 12345


class TestGetStories:
    """Tests for get_stories concurrent fetching."""

    @pytest.mark.asyncio
    async def test_filters_out_exceptions(self, caplog):
        """get_stories gracefully handles individual story fetch errors."""
        from taggernews.domain.story import Story

        client = HNClient()

        story_1 = Story(
            id=None, hn_id=1, title="Story 1", url=None,
            score=10, author="a", comment_count=0,
            hn_created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )

        async def mock_get_story(sid):
            if sid == 2:
                raise aiohttp.ClientError("boom")
            return story_1 if sid == 1 else None

        client.get_story = mock_get_story

        with caplog.at_level(logging.ERROR):
            stories = await client.get_stories([1, 2, 3])

        # Only story 1 should be returned (2 raised, 3 was None)
        assert len(stories) == 1

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        """get_stories with empty list returns empty list."""
        client = HNClient()
        stories = await client.get_stories([])
        assert stories == []


class TestGetTopStoryIds:
    """Tests for story ID fetching edge cases."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_failure(self):
        """get_top_story_ids returns [] when API fails."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=None)

        result = await client.get_top_story_ids()
        assert result == []

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        """get_top_story_ids respects limit parameter."""
        client = HNClient()
        client._fetch_with_retry = AsyncMock(return_value=list(range(500)))

        result = await client.get_top_story_ids(limit=10)
        assert len(result) == 10

    @pytest.mark.asyncio
    async def test_no_limit_returns_all(self):
        """get_top_story_ids returns all when no limit."""
        client = HNClient()
        ids = list(range(500))
        client._fetch_with_retry = AsyncMock(return_value=ids)

        result = await client.get_top_story_ids()
        assert len(result) == 500


class TestGetAllStoryIds:
    """Tests for get_all_story_ids deduplication."""

    @pytest.mark.asyncio
    async def test_deduplicates_ids(self):
        """get_all_story_ids removes duplicates between top and new."""
        client = HNClient()
        client.get_top_story_ids = AsyncMock(return_value=[1, 2, 3])
        client.get_new_story_ids = AsyncMock(return_value=[2, 3, 4])

        result = await client.get_all_story_ids()
        assert result == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_preserves_order_top_first(self):
        """get_all_story_ids preserves top stories order first."""
        client = HNClient()
        client.get_top_story_ids = AsyncMock(return_value=[10, 20, 30])
        client.get_new_story_ids = AsyncMock(return_value=[25, 30, 40])

        result = await client.get_all_story_ids()
        assert result == [10, 20, 30, 25, 40]

    @pytest.mark.asyncio
    async def test_limit_applied_after_dedup(self):
        """get_all_story_ids applies limit after deduplication."""
        client = HNClient()
        client.get_top_story_ids = AsyncMock(return_value=[1, 2, 3])
        client.get_new_story_ids = AsyncMock(return_value=[3, 4, 5])

        result = await client.get_all_story_ids(limit=3)
        assert len(result) == 3
        assert result == [1, 2, 3]


class TestGetItemsBatch:
    """Tests for get_items_batch filtering."""

    @pytest.mark.asyncio
    async def test_filters_deleted_items(self):
        """get_items_batch skips deleted items."""
        client = HNClient()

        async def mock_get_item(item_id):
            if item_id == 1:
                return {"id": 1, "type": "story", "deleted": True, "time": 1700000000}
            return {
                "id": 2, "type": "story", "title": "OK", "time": 1700000000,
            }

        client.get_item = mock_get_item

        stories = await client.get_items_batch([1, 2])
        assert len(stories) == 1
        assert stories[0].hn_id == 2

    @pytest.mark.asyncio
    async def test_filters_dead_items(self):
        """get_items_batch skips dead items."""
        client = HNClient()

        async def mock_get_item(item_id):
            return {"id": item_id, "type": "story", "dead": True, "time": 1700000000}

        client.get_item = mock_get_item

        stories = await client.get_items_batch([1])
        assert len(stories) == 0

    @pytest.mark.asyncio
    async def test_filters_non_story_types(self):
        """get_items_batch only returns items matching filter_type."""
        client = HNClient()

        items = {
            1: {"id": 1, "type": "story", "title": "A", "time": 1700000000},
            2: {"id": 2, "type": "comment", "text": "hello"},
            3: {"id": 3, "type": "job", "title": "Hiring"},
        }
        client.get_item = AsyncMock(side_effect=lambda iid: items.get(iid))

        stories = await client.get_items_batch([1, 2, 3])
        assert len(stories) == 1
        assert stories[0].hn_id == 1

    @pytest.mark.asyncio
    async def test_handles_none_items(self):
        """get_items_batch handles None (deleted/missing) items."""
        client = HNClient()
        client.get_item = AsyncMock(return_value=None)

        stories = await client.get_items_batch([1, 2, 3])
        assert len(stories) == 0

    @pytest.mark.asyncio
    async def test_handles_exceptions_in_batch(self):
        """get_items_batch silently skips items that raise exceptions."""
        client = HNClient()

        async def mock_get_item(item_id):
            if item_id == 2:
                raise aiohttp.ClientError("fail")
            return {"id": item_id, "type": "story", "title": "T", "time": 1700000000}

        client.get_item = mock_get_item

        stories = await client.get_items_batch([1, 2, 3])
        # Items 1 and 3 should succeed, 2 should be skipped
        assert len(stories) == 2


class TestSessionManagement:
    """Tests for HNClient session lifecycle."""

    @pytest.mark.asyncio
    async def test_close_when_no_session(self):
        """close() does not raise when no session exists."""
        client = HNClient()
        await client.close()  # Should not raise

    @pytest.mark.asyncio
    async def test_close_when_already_closed(self):
        """close() does not raise when session already closed."""
        client = HNClient()
        mock_session = MagicMock()
        mock_session.closed = True
        client._session = mock_session

        await client.close()  # Should not raise
        mock_session.close.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_session_creates_new_when_closed(self):
        """_get_session creates a new session when previous is closed."""
        client = HNClient()
        mock_session = MagicMock()
        mock_session.closed = True
        client._session = mock_session

        session = await client._get_session()
        assert session is not mock_session  # Should be a new session

    @pytest.mark.asyncio
    async def test_get_session_reuses_open_session(self):
        """_get_session returns existing session when not closed."""
        client = HNClient()
        mock_session = MagicMock()
        mock_session.closed = False
        client._session = mock_session

        session = await client._get_session()
        assert session is mock_session
