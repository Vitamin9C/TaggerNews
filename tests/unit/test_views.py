"""Tests for web view utility functions."""

from taggernews.api.web.views import _parse_json_list


class TestParseJsonList:
    """Tests for _parse_json_list."""

    def test_valid_string_array(self):
        assert _parse_json_list('["Tech", "Business"]') == ["Tech", "Business"]

    def test_empty_string(self):
        assert _parse_json_list("") == []

    def test_none_input(self):
        assert _parse_json_list(None) == []

    def test_invalid_json(self):
        assert _parse_json_list("not json") == []

    def test_json_object_returns_empty(self):
        assert _parse_json_list('{"key": "value"}') == []

    def test_json_string_returns_empty(self):
        assert _parse_json_list('"just a string"') == []

    def test_json_number_returns_empty(self):
        assert _parse_json_list("42") == []

    def test_filters_non_string_elements(self):
        assert _parse_json_list('["Tech", 123, null, true]') == ["Tech"]

    def test_empty_array(self):
        assert _parse_json_list("[]") == []

    def test_single_element(self):
        assert _parse_json_list('["AI/ML"]') == ["AI/ML"]
