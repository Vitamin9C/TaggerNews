"""Tests for StoryRepository date range helpers."""

from datetime import UTC

from taggernews.repositories.story_repo import StoryRepository


class TestDateRangeHelpers:
    """Tests for get_today_range and get_this_week_range."""

    def setup_method(self):
        # These are pure methods that don't use the session
        self.repo = StoryRepository(session=None)  # type: ignore[arg-type]

    def test_get_today_range_returns_utc(self):
        start, end = self.repo.get_today_range()
        assert start.tzinfo == UTC
        assert end.tzinfo == UTC

    def test_get_today_range_start_is_midnight(self):
        start, _ = self.repo.get_today_range()
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0
        assert start.microsecond == 0

    def test_get_today_range_start_before_end(self):
        start, end = self.repo.get_today_range()
        assert start <= end

    def test_get_this_week_range_returns_utc(self):
        start, end = self.repo.get_this_week_range()
        assert start.tzinfo == UTC
        assert end.tzinfo == UTC

    def test_get_this_week_range_starts_on_monday(self):
        start, _ = self.repo.get_this_week_range()
        # weekday() returns 0 for Monday
        assert start.weekday() == 0

    def test_get_this_week_range_start_is_midnight(self):
        start, _ = self.repo.get_this_week_range()
        assert start.hour == 0
        assert start.minute == 0
        assert start.second == 0

    def test_get_this_week_range_start_before_end(self):
        start, end = self.repo.get_this_week_range()
        assert start <= end
