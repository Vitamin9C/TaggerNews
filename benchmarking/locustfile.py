"""Locust load testing script for TaggerNews."""

import random

from locust import HttpUser, between, task

# Common tags for random filtering
SAMPLE_TAGS = [
    "Tech",
    "Business",
    "AI/ML",
    "Web",
    "Python",
    "Startups",
    "Security",
    "Open Source",
]


class TaggerNewsUser(HttpUser):
    """Simulated user for load testing TaggerNews."""

    wait_time = between(1, 3)  # Wait 1-3 seconds between tasks

    @task(3)
    def fetch_top_stories_today(self) -> None:
        """Fetch top stories for today - most common operation."""
        self.client.get("/?period=today")

    @task(2)
    def fetch_top_stories_week(self) -> None:
        """Fetch top stories for this week."""
        self.client.get("/?period=week")

    @task(2)
    def fetch_all_stories(self) -> None:
        """Fetch all stories without filters."""
        self.client.get("/")

    @task(1)
    def fetch_stories_with_random_tag(self) -> None:
        """Fetch stories filtered by a random tag."""
        tag = random.choice(SAMPLE_TAGS)
        self.client.get(f"/?tag={tag}")

    @task(1)
    def fetch_stories_tag_and_period(self) -> None:
        """Fetch stories with both tag and period filter."""
        tag = random.choice(SAMPLE_TAGS)
        period = random.choice(["today", "week"])
        self.client.get(f"/?tag={tag}&period={period}")

    @task(1)
    def load_more_stories(self) -> None:
        """Simulate infinite scroll - load more stories."""
        offset = random.choice([30, 60, 90])
        self.client.get(f"/stories/more?offset={offset}&limit=30")

    @task(1)
    def filter_stories(self) -> None:
        """Simulate filter change via HTMX endpoint."""
        tag = random.choice(SAMPLE_TAGS)
        self.client.get(f"/stories/filter?tag={tag}")
