"""Edge case tests for Story domain entity: malformed data, boundary values."""

from datetime import UTC, datetime

import pytest

from taggernews.domain.story import Story


class TestFromHnApiMalformedData:
    """Tests for Story.from_hn_api with malformed/unexpected API data."""

    def test_missing_id_raises_key_error(self):
        """from_hn_api raises KeyError when 'id' is missing."""
        with pytest.raises(KeyError):
            Story.from_hn_api({"title": "No ID", "type": "story"})

    def test_zero_timestamp(self):
        """from_hn_api handles time=0 (Unix epoch)."""
        story = Story.from_hn_api({"id": 1, "type": "story", "time": 0})
        assert story.hn_created_at == datetime(1970, 1, 1, tzinfo=UTC)

    def test_missing_time_defaults_to_epoch(self):
        """from_hn_api uses epoch when time is missing."""
        story = Story.from_hn_api({"id": 1, "type": "story"})
        assert story.hn_created_at == datetime(1970, 1, 1, tzinfo=UTC)

    def test_negative_score(self):
        """from_hn_api handles negative scores (dead/flagged stories)."""
        story = Story.from_hn_api({
            "id": 1, "type": "story", "score": -5, "time": 1700000000,
        })
        assert story.score == -5

    def test_very_large_score(self):
        """from_hn_api handles very large scores."""
        story = Story.from_hn_api({
            "id": 1, "type": "story", "score": 999999, "time": 1700000000,
        })
        assert story.score == 999999

    def test_very_long_title(self):
        """from_hn_api handles extremely long titles."""
        long_title = "A" * 5000
        story = Story.from_hn_api({
            "id": 1, "type": "story", "title": long_title, "time": 1700000000,
        })
        assert len(story.title) == 5000

    def test_empty_string_author(self):
        """from_hn_api handles empty string 'by' field."""
        story = Story.from_hn_api({
            "id": 1, "type": "story", "by": "", "time": 1700000000,
        })
        assert story.author == ""

    def test_special_characters_in_title(self):
        """from_hn_api preserves special characters in title."""
        title = '<script>alert("xss")</script> & "quotes"'
        story = Story.from_hn_api({
            "id": 1, "type": "story", "title": title, "time": 1700000000,
        })
        assert story.title == title

    def test_unicode_in_title(self):
        """from_hn_api handles Unicode characters."""
        title = "日本語のタイトル 🚀 émojis"
        story = Story.from_hn_api({
            "id": 1, "type": "story", "title": title, "time": 1700000000,
        })
        assert story.title == title

    def test_very_large_hn_id(self):
        """from_hn_api handles very large HN IDs."""
        story = Story.from_hn_api({
            "id": 99999999, "type": "story", "time": 1700000000,
        })
        assert story.hn_id == 99999999

    def test_zero_descendants(self):
        """from_hn_api correctly maps descendants to comment_count."""
        story = Story.from_hn_api({
            "id": 1, "type": "story", "descendants": 0, "time": 1700000000,
        })
        assert story.comment_count == 0

    def test_large_future_timestamp(self):
        """from_hn_api handles far-future timestamps."""
        # Year 2100
        future_ts = 4102444800
        story = Story.from_hn_api({"id": 1, "type": "story", "time": future_ts})
        assert story.hn_created_at.year == 2100
        assert story.hn_created_at.tzinfo == UTC

    def test_extra_fields_ignored(self):
        """from_hn_api ignores extra/unknown fields."""
        story = Story.from_hn_api({
            "id": 1, "type": "story", "time": 1700000000,
            "kids": [100, 200], "text": "Some text", "parent": 0,
        })
        assert story.hn_id == 1


class TestSanitizeUrlEdgeCases:
    """Additional edge cases for _sanitize_url."""

    def test_whitespace_only_url(self):
        """Empty-ish URLs return None."""
        assert Story._sanitize_url("   ") is None

    def test_url_with_query_params(self):
        """HTTPS URLs with query params are preserved."""
        url = "https://example.com/path?q=test&page=1#anchor"
        assert Story._sanitize_url(url) == url

    def test_url_with_port(self):
        """URLs with port numbers are allowed."""
        url = "http://localhost:8080/api"
        assert Story._sanitize_url(url) == url

    def test_vbscript_url_rejected(self):
        """vbscript: URLs are rejected."""
        assert Story._sanitize_url("vbscript:msgbox('hi')") is None

    def test_file_url_rejected(self):
        """file:// URLs are rejected."""
        assert Story._sanitize_url("file:///etc/passwd") is None

    def test_url_with_encoded_javascript(self):
        """URL-encoded javascript: scheme should still be caught by urlparse."""
        # urlparse normalizes the scheme, so this depends on input
        result = Story._sanitize_url("javascript%3Aalert(1)")
        # This will be treated as a relative URL with no scheme
        # urlparse returns empty scheme for this -> not in ("http", "https")
        assert result is None

    def test_https_url_with_unicode(self):
        """HTTPS URLs with Unicode in path are allowed."""
        url = "https://example.com/日本語"
        assert Story._sanitize_url(url) == url
