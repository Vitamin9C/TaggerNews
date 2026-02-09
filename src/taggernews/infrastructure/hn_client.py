"""Hacker News Firebase API client."""

import asyncio
import logging
from typing import Any

import aiohttp
from aiohttp import ClientTimeout

from taggernews.config import get_settings
from taggernews.domain.story import Story

logger = logging.getLogger(__name__)
settings = get_settings()


class HNClient:
    """Async client for Hacker News Firebase API."""

    def __init__(
        self,
        base_url: str | None = None,
        max_concurrent: int = 10,
        timeout_seconds: int = 30,
    ) -> None:
        """Initialize HN client.

        Args:
            base_url: HN API base URL (defaults to config)
            max_concurrent: Maximum concurrent requests
            timeout_seconds: Request timeout in seconds
        """
        self.base_url = base_url or settings.hn_api_base_url
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = ClientTimeout(total=timeout_seconds)
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=self.timeout)
        return self._session

    async def close(self) -> None:
        """Close the aiohttp session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def _fetch_with_retry(
        self,
        url: str,
        max_retries: int = 3,
        base_delay: float = 1.0,
    ) -> dict[str, Any] | None:
        """Fetch URL with exponential backoff retry.

        Args:
            url: URL to fetch
            max_retries: Maximum retry attempts
            base_delay: Base delay in seconds for exponential backoff

        Returns:
            JSON response or None if failed
        """
        session = await self._get_session()

        async with self.semaphore:
            for attempt in range(max_retries):
                try:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return await response.json()
                        elif response.status == 429:
                            # Rate limited - wait longer
                            delay = base_delay * (2**attempt) * 2
                            logger.warning(f"Rate limited, waiting {delay}s")
                            await asyncio.sleep(delay)
                        else:
                            logger.error(f"HTTP {response.status} for {url}")
                            return None
                except TimeoutError:
                    logger.warning(f"Timeout fetching {url}, attempt {attempt + 1}")
                except aiohttp.ClientError as e:
                    logger.warning(f"Client error: {e}, attempt {attempt + 1}")

                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    await asyncio.sleep(delay)

            logger.error(f"Failed to fetch {url} after {max_retries} attempts")
            return None

    async def get_top_story_ids(self, limit: int | None = None) -> list[int]:
        """Get top story IDs from HN.

        Args:
            limit: Maximum number of story IDs to return

        Returns:
            List of story IDs
        """
        url = f"{self.base_url}/topstories.json"
        data = await self._fetch_with_retry(url)

        if data is None:
            return []

        story_ids = data[:limit] if limit else data
        logger.info(f"Fetched {len(story_ids)} top story IDs")
        return story_ids

    async def get_new_story_ids(self, limit: int | None = None) -> list[int]:
        """Get new story IDs from HN.

        Args:
            limit: Maximum number of story IDs to return

        Returns:
            List of story IDs
        """
        url = f"{self.base_url}/newstories.json"
        data = await self._fetch_with_retry(url)

        if data is None:
            return []

        story_ids = data[:limit] if limit else data
        logger.info(f"Fetched {len(story_ids)} new story IDs")
        return story_ids

    async def get_all_story_ids(self, limit: int | None = None) -> list[int]:
        """Get combined story IDs from top and new stories.

        Args:
            limit: Maximum number of story IDs to return

        Returns:
            List of unique story IDs
        """
        top_ids = await self.get_top_story_ids()
        new_ids = await self.get_new_story_ids()

        # Combine and deduplicate, preserving order
        seen = set()
        all_ids = []
        for sid in top_ids + new_ids:
            if sid not in seen:
                seen.add(sid)
                all_ids.append(sid)

        result = all_ids[:limit] if limit else all_ids
        logger.info(f"Combined {len(result)} unique story IDs")
        return result

    async def get_story(self, story_id: int) -> Story | None:
        """Get a single story by ID.

        Args:
            story_id: HN story ID

        Returns:
            Story domain object or None
        """
        url = f"{self.base_url}/item/{story_id}.json"
        data = await self._fetch_with_retry(url)

        if data is None or data.get("type") != "story":
            return None

        return Story.from_hn_api(data)

    async def get_stories(self, story_ids: list[int]) -> list[Story]:
        """Fetch multiple stories concurrently.

        Args:
            story_ids: List of HN story IDs

        Returns:
            List of Story domain objects
        """
        tasks = [self.get_story(sid) for sid in story_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        stories = []
        for result in results:
            if isinstance(result, Story):
                stories.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Error fetching story: {result}")

        logger.info(f"Successfully fetched {len(stories)}/{len(story_ids)} stories")
        return stories

    async def get_max_item_id(self) -> int | None:
        """Get the current maximum item ID from HN.

        This is used to know the upper bound for scraping.
        New items are assigned incrementing IDs.

        Returns:
            Maximum item ID or None if request failed
        """
        url = f"{self.base_url}/maxitem.json"
        data = await self._fetch_with_retry(url)

        if data is None:
            logger.error(f"Failed to fetch max item ID from {url}")
            return None

        if not isinstance(data, int):
            logger.warning(
                f"Unexpected data type for max item ID: "
                f"{type(data)}, value: {data}"
            )
            return None

        logger.debug(f"Current HN max item ID: {data}")
        return data

    async def get_item(self, item_id: int) -> dict[str, Any] | None:
        """Get any item by ID (story, comment, job, poll, etc.).

        Returns raw dict to allow type checking by caller.

        Args:
            item_id: HN item ID

        Returns:
            Raw item dict or None if not found/deleted
        """
        url = f"{self.base_url}/item/{item_id}.json"
        data = await self._fetch_with_retry(url)
        return data

    async def get_items_batch(
        self,
        item_ids: list[int],
        filter_type: str = "story",
    ) -> list[Story]:
        """Fetch multiple items and filter by type.

        Args:
            item_ids: List of HN item IDs to fetch
            filter_type: Only return items of this type (default: story)

        Returns:
            List of Story domain objects (only stories, not comments/jobs)
        """
        async def fetch_and_filter(item_id: int) -> Story | None:
            data = await self.get_item(item_id)
            if data is None:
                return None
            if data.get("type") != filter_type:
                return None
            if data.get("deleted") or data.get("dead"):
                return None
            return Story.from_hn_api(data)

        tasks = [fetch_and_filter(iid) for iid in item_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        stories = []
        for result in results:
            if isinstance(result, Story):
                stories.append(result)

        return stories

    async def get_best_story_ids(self, limit: int | None = None) -> list[int]:
        """Get best story IDs from HN.

        Args:
            limit: Maximum number of story IDs to return

        Returns:
            List of story IDs
        """
        url = f"{self.base_url}/beststories.json"
        data = await self._fetch_with_retry(url)

        if data is None:
            return []

        story_ids = data[:limit] if limit else data
        logger.info(f"Fetched {len(story_ids)} best story IDs")
        return story_ids
