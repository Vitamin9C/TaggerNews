"""Edge case tests for web views: date parsing, filter combinations."""

from datetime import datetime

from taggernews.api.web.views import _parse_json_list, parse_date


class TestParseDateEdgeCases:
    """Tests for parse_date function."""

    def test_valid_date(self):
        result = parse_date("2026-01-15")
        assert isinstance(result, datetime)
        assert result.year == 2026
        assert result.month == 1
        assert result.day == 15

    def test_none_returns_none(self):
        assert parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert parse_date("") is None

    def test_invalid_format_returns_none(self):
        assert parse_date("01/15/2026") is None

    def test_invalid_date_returns_none(self):
        assert parse_date("2026-13-45") is None

    def test_partial_date_returns_none(self):
        assert parse_date("2026-01") is None

    def test_date_with_time_returns_none(self):
        """YYYY-MM-DD format only, no time component."""
        assert parse_date("2026-01-15T12:00:00") is None

    def test_iso_format_returns_none(self):
        """ISO format with timezone is not accepted."""
        assert parse_date("2026-01-15T12:00:00Z") is None

    def test_garbage_string_returns_none(self):
        assert parse_date("not-a-date") is None

    def test_leap_year_date(self):
        result = parse_date("2024-02-29")
        assert result is not None
        assert result.day == 29

    def test_non_leap_year_feb_29(self):
        """Feb 29 on non-leap year returns None."""
        assert parse_date("2026-02-29") is None


class TestParseJsonListEdgeCases:
    """Additional edge cases for _parse_json_list."""

    def test_deeply_nested_array(self):
        """Nested arrays: inner arrays are not strings, so filtered."""
        assert _parse_json_list('[["nested"]]') == []

    def test_mixed_types_with_booleans(self):
        """Boolean values are filtered out."""
        assert _parse_json_list('["Tech", true, false]') == ["Tech"]

    def test_whitespace_json(self):
        """JSON with extra whitespace still parses."""
        assert _parse_json_list('  [  "Tech"  ]  ') == ["Tech"]

    def test_unicode_strings(self):
        """Unicode strings are preserved."""
        assert _parse_json_list('["日本語", "émojis"]') == ["日本語", "émojis"]

    def test_very_long_array(self):
        """Large arrays parse correctly."""
        import json
        big_list = [f"tag{i}" for i in range(1000)]
        result = _parse_json_list(json.dumps(big_list))
        assert len(result) == 1000

    def test_empty_string_elements(self):
        """Empty strings in array are preserved."""
        assert _parse_json_list('["", "Tech", ""]') == ["", "Tech", ""]

    def test_null_json(self):
        """JSON null returns empty list."""
        assert _parse_json_list("null") == []

    def test_json_true(self):
        """JSON true returns empty list (not a list)."""
        assert _parse_json_list("true") == []

    def test_json_array_of_numbers(self):
        """Array of numbers returns empty (no strings)."""
        assert _parse_json_list("[1, 2, 3]") == []
