"""Edge case tests for Settings configuration."""

from unittest.mock import patch

from taggernews.config import Settings


class TestSettingsDefaults:
    """Tests for Settings default values."""

    def test_default_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
            assert s.environment == "development"

    def test_default_database_url(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
            assert "postgresql" in s.database_url

    def test_default_openai_key_empty(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
            assert s.openai_api_key == ""

    def test_default_api_key_empty(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
            assert s.api_key == ""

    def test_default_scrape_interval(self):
        with patch.dict("os.environ", {}, clear=True):
            s = Settings(_env_file=None)
            assert s.scrape_interval_minutes == 5


class TestSettingsProperties:
    """Tests for computed properties."""

    def test_is_production_true(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=True):
            s = Settings(_env_file=None)
            assert s.is_production is True

    def test_is_production_false_for_development(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}, clear=True):
            s = Settings(_env_file=None)
            assert s.is_production is False

    def test_is_production_false_for_arbitrary(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "staging"}, clear=True):
            s = Settings(_env_file=None)
            assert s.is_production is False

    def test_backfill_days_production(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=True):
            s = Settings(_env_file=None)
            assert s.scraper_backfill_days == s.scraper_backfill_days_prod
            assert s.scraper_backfill_days == 30

    def test_backfill_days_development(self):
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}, clear=True):
            s = Settings(_env_file=None)
            assert s.scraper_backfill_days == s.scraper_backfill_days_dev
            assert s.scraper_backfill_days == 7


class TestSettingsEnvOverrides:
    """Tests for environment variable overrides."""

    def test_override_scrape_interval(self):
        with patch.dict("os.environ", {"SCRAPE_INTERVAL_MINUTES": "15"}, clear=True):
            s = Settings(_env_file=None)
            assert s.scrape_interval_minutes == 15

    def test_override_top_stories_count(self):
        with patch.dict("os.environ", {"TOP_STORIES_COUNT": "100"}, clear=True):
            s = Settings(_env_file=None)
            assert s.top_stories_count == 100

    def test_override_agent_auto_approve(self):
        with patch.dict("os.environ", {"AGENT_ENABLE_AUTO_APPROVE": "true"}, clear=True):
            s = Settings(_env_file=None)
            assert s.agent_enable_auto_approve is True

    def test_case_insensitive_env_vars(self):
        """Pydantic Settings with case_sensitive=False accepts any case."""
        with patch.dict("os.environ", {"environment": "production"}, clear=True):
            s = Settings(_env_file=None)
            assert s.environment == "production"

    def test_override_batch_sizes(self):
        with patch.dict("os.environ", {
            "SCRAPER_BACKFILL_BATCH_SIZE": "500",
            "SCRAPER_CONTINUOUS_BATCH_SIZE": "200",
        }, clear=True):
            s = Settings(_env_file=None)
            assert s.scraper_backfill_batch_size == 500
            assert s.scraper_continuous_batch_size == 200
