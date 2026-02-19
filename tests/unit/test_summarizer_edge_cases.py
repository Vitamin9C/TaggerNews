"""Edge case tests for SummarizerService: OpenAI failures, malformed responses."""

import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taggernews.domain.story import Story
from taggernews.services.summarizer import SummarizerService, StoryAnalysis, TagsOutput


def _make_story(**kwargs) -> Story:
    """Create a Story with sensible defaults."""
    defaults = {
        "id": 1,
        "hn_id": 12345,
        "title": "Test Story",
        "url": "https://example.com",
        "score": 100,
        "author": "testuser",
        "comment_count": 50,
        "hn_created_at": datetime(2026, 1, 15, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return Story(**defaults)


class TestSummarizeStoryFailures:
    """Tests for summarize_story error handling."""

    @pytest.mark.asyncio
    async def test_no_api_key_returns_none(self, caplog):
        """Returns None when OpenAI API key is not configured."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="", model="gpt-4o-mini")

            with caplog.at_level(logging.WARNING):
                result = await service.summarize_story(_make_story())

            assert result is None
            assert "API key not configured" in caplog.text

    @pytest.mark.asyncio
    async def test_openai_exception_returns_none(self, caplog):
        """Returns None when OpenAI raises an exception."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="test-key", model="gpt-4o-mini")
            service.client = MagicMock()
            service.client.responses = MagicMock()
            service.client.responses.parse = AsyncMock(
                side_effect=Exception("OpenAI rate limit")
            )

            with caplog.at_level(logging.ERROR):
                result = await service.summarize_story(_make_story())

            assert result is None
            assert "Failed to summarize" in caplog.text

    @pytest.mark.asyncio
    async def test_timeout_error_returns_none(self, caplog):
        """Returns None when OpenAI request times out."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="test-key", model="gpt-4o-mini")
            service.client = MagicMock()
            service.client.responses = MagicMock()
            service.client.responses.parse = AsyncMock(
                side_effect=TimeoutError("request timed out")
            )

            with caplog.at_level(logging.ERROR):
                result = await service.summarize_story(_make_story())

            assert result is None

    @pytest.mark.asyncio
    async def test_story_without_url_uses_placeholder(self):
        """Story with no URL uses 'No URL provided' in prompt."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="test-key", model="gpt-4o-mini")

            analysis = StoryAnalysis(
                summary="Test summary",
                tags=TagsOutput(l1_tags=["Tech"], l2_tags=["AI/ML"], l3_tags=[]),
            )
            mock_response = MagicMock()
            mock_response.output_text = analysis.model_dump_json()
            service.client = MagicMock()
            service.client.responses = MagicMock()
            service.client.responses.parse = AsyncMock(return_value=mock_response)

            result = await service.summarize_story(_make_story(url=None))

            assert result is not None
            summary, flat_tags = result
            assert summary.text == "Test summary"

    @pytest.mark.asyncio
    async def test_story_with_none_id_gets_zero_story_id(self):
        """Summary story_id defaults to 0 when story.id is None."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="test-key", model="gpt-4o-mini")

            analysis = StoryAnalysis(
                summary="Test",
                tags=TagsOutput(),
            )
            mock_response = MagicMock()
            mock_response.output_text = analysis.model_dump_json()
            service.client = MagicMock()
            service.client.responses = MagicMock()
            service.client.responses.parse = AsyncMock(return_value=mock_response)

            result = await service.summarize_story(_make_story(id=None))

            assert result is not None
            summary, _ = result
            assert summary.story_id == 0


class TestSummarizeStories:
    """Tests for summarize_stories batch processing."""

    @pytest.mark.asyncio
    async def test_empty_list_returns_empty(self):
        """summarize_stories with empty list returns empty."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="test-key", model="gpt-4o-mini")

            results = await service.summarize_stories([])
            assert results == []

    @pytest.mark.asyncio
    async def test_partial_failures_skipped(self):
        """summarize_stories skips stories that fail to summarize."""
        with patch("taggernews.services.summarizer.settings") as mock_settings:
            mock_settings.openai_api_key = "test-key"
            mock_settings.summarization_model = "gpt-4o-mini"
            service = SummarizerService(api_key="test-key", model="gpt-4o-mini")

            call_count = 0

            async def mock_summarize(story):
                nonlocal call_count
                call_count += 1
                if call_count == 2:
                    return None  # Second story fails
                return (
                    MagicMock(text="summary", model="gpt-4o-mini"),
                    MagicMock(l1_tags=["Tech"]),
                )

            service.summarize_story = mock_summarize

            stories = [_make_story(hn_id=i) for i in range(3)]
            results = await service.summarize_stories(stories)

            assert len(results) == 2  # 3 stories, 1 failed


class TestStoryAnalysisModel:
    """Tests for StoryAnalysis Pydantic model."""

    def test_empty_tags(self):
        """StoryAnalysis accepts empty tag lists."""
        analysis = StoryAnalysis(
            summary="Test",
            tags=TagsOutput(l1_tags=[], l2_tags=[], l3_tags=[]),
        )
        assert analysis.tags.l1_tags == []

    def test_valid_analysis(self):
        """StoryAnalysis parses valid data."""
        analysis = StoryAnalysis(
            summary="A test summary.",
            tags=TagsOutput(
                l1_tags=["Tech", "Business"],
                l2_tags=["AI/ML"],
                l3_tags=["OpenAI"],
            ),
        )
        assert len(analysis.tags.l1_tags) == 2
        assert analysis.summary == "A test summary."
