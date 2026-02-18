"""Tests for security fixes."""

from unittest.mock import AsyncMock, patch

import pytest

from taggernews.domain.story import Story


class TestUrlSanitization:
    """Tests for Story._sanitize_url XSS prevention."""

    def test_http_url_allowed(self):
        assert Story._sanitize_url("http://example.com") == "http://example.com"

    def test_https_url_allowed(self):
        assert Story._sanitize_url("https://example.com") == "https://example.com"

    def test_javascript_url_rejected(self):
        assert Story._sanitize_url("javascript:alert(1)") is None

    def test_javascript_mixed_case_rejected(self):
        assert Story._sanitize_url("JavaScript:alert(1)") is None

    def test_data_url_rejected(self):
        assert Story._sanitize_url("data:text/html,<script>alert(1)</script>") is None

    def test_ftp_url_rejected(self):
        assert Story._sanitize_url("ftp://example.com/file") is None

    def test_empty_string_returns_none(self):
        assert Story._sanitize_url("") is None

    def test_none_returns_none(self):
        assert Story._sanitize_url(None) is None

    def test_from_hn_api_sanitizes_url(self):
        data = {
            "id": 1,
            "title": "Test",
            "url": "javascript:alert(document.cookie)",
            "time": 1700000000,
            "type": "story",
        }
        story = Story.from_hn_api(data)
        assert story.url is None

    def test_from_hn_api_keeps_https_url(self):
        data = {
            "id": 1,
            "title": "Test",
            "url": "https://example.com/article",
            "time": 1700000000,
            "type": "story",
        }
        story = Story.from_hn_api(data)
        assert story.url == "https://example.com/article"


class TestApiKeyAuth:
    """Tests for API key authentication dependency."""

    @pytest.mark.asyncio
    async def test_no_api_key_configured_allows_anonymous(self):
        """When API_KEY is empty, auth is skipped."""
        from taggernews.api.dependencies import require_api_key

        with patch("taggernews.api.dependencies.get_settings") as mock_settings:
            mock_settings.return_value = AsyncMock(api_key="")
            result = await require_api_key(api_key=None)
            assert result == "anonymous"

    @pytest.mark.asyncio
    async def test_valid_api_key_passes(self):
        """Correct API key passes authentication."""
        from taggernews.api.dependencies import require_api_key

        with patch("taggernews.api.dependencies.get_settings") as mock_settings:
            mock_settings.return_value = AsyncMock(api_key="secret-key-123")
            result = await require_api_key(api_key="secret-key-123")
            assert result == "secret-key-123"

    @pytest.mark.asyncio
    async def test_wrong_api_key_rejected(self):
        """Wrong API key returns 403."""
        from fastapi import HTTPException

        from taggernews.api.dependencies import require_api_key

        with patch("taggernews.api.dependencies.get_settings") as mock_settings:
            mock_settings.return_value = AsyncMock(api_key="secret-key-123")
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key="wrong-key")
            assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_missing_api_key_rejected(self):
        """Missing API key when configured returns 403."""
        from fastapi import HTTPException

        from taggernews.api.dependencies import require_api_key

        with patch("taggernews.api.dependencies.get_settings") as mock_settings:
            mock_settings.return_value = AsyncMock(api_key="secret-key-123")
            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(api_key=None)
            assert exc_info.value.status_code == 403
