"""TaggerNews configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Environment
    environment: str = "development"

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/taggernews"

    # OpenAI
    openai_api_key: str = ""

    # HN Scraper
    hn_api_base_url: str = "https://hacker-news.firebaseio.com/v0"
    scrape_interval_minutes: int = 5
    top_stories_count: int = 30

    # Scheduler
    scrape_interval_hours: int = 1
    startup_backfill_days_dev: int = 0
    startup_backfill_days_prod: int = 21

    # Summarization
    summarization_model: str = "gpt-4o-mini"
    summarization_batch_size: int = 5

    # Dev-only: Manual tag extension (for testing L2/L3 tag creation)
    enable_manual_tag_extension: bool = False

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def startup_backfill_days(self) -> int:
        """Get backfill days based on environment."""
        return (
            self.startup_backfill_days_prod
            if self.is_production
            else self.startup_backfill_days_dev
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
