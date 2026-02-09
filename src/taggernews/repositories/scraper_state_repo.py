"""Repository for scraper state tracking."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.infrastructure.models import ScraperStateModel, StoryModel


class ScraperStateRepository:
    """Repository for managing scraper state and efficient story lookups."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    async def get_state(self, state_type: str) -> ScraperStateModel | None:
        """Get scraper state by type.

        Args:
            state_type: Either 'backfill' or 'continuous'

        Returns:
            ScraperStateModel if exists, None otherwise
        """
        stmt = select(ScraperStateModel).where(
            ScraperStateModel.state_type == state_type
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create_state_with_lock(
        self,
        state_type: str,
        initial_item_id: int,
    ) -> tuple[ScraperStateModel, bool]:
        """Get existing state or create new one with advisory lock.

        Uses PostgreSQL advisory locks to prevent race conditions when
        multiple jobs try to initialize state simultaneously.

        Args:
            state_type: Either 'backfill' or 'continuous'
            initial_item_id: Initial position if creating new state

        Returns:
            Tuple of (state, was_created)
        """
        # Hash state_type to get a consistent lock ID
        lock_id = hash(f"scraper_state_{state_type}") % 2147483647

        # Try to acquire advisory lock (blocks until available)
        # Lock is automatically released at transaction end
        await self.session.execute(
            select(func.pg_advisory_xact_lock(lock_id))
        )

        # Now that we have the lock, check if state exists
        state = await self.get_state(state_type)

        if state:
            return state, False

        # Create new state
        state = ScraperStateModel(
            state_type=state_type,
            current_item_id=initial_item_id,
            status="active",
            last_run_at=datetime.now(timezone.utc),
        )
        self.session.add(state)
        await self.session.flush()
        return state, True

    async def create_or_update_state(
        self,
        state_type: str,
        current_item_id: int,
        target_timestamp: datetime | None = None,
        status: str = "active",
    ) -> ScraperStateModel:
        """Create or update scraper state.

        Args:
            state_type: Either 'backfill' or 'continuous'
            current_item_id: Current position in item ID sequence
            target_timestamp: For backfill, the cutoff timestamp
            status: 'active', 'completed', or 'paused'

        Returns:
            The created or updated ScraperStateModel
        """
        existing = await self.get_state(state_type)

        if existing:
            existing.current_item_id = current_item_id
            if target_timestamp is not None:
                existing.target_timestamp = target_timestamp
            existing.status = status
            existing.last_run_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing

        state = ScraperStateModel(
            state_type=state_type,
            current_item_id=current_item_id,
            target_timestamp=target_timestamp,
            status=status,
            last_run_at=datetime.now(timezone.utc),
        )
        self.session.add(state)
        await self.session.flush()
        return state

    async def increment_counters(
        self,
        state_type: str,
        items_processed: int = 0,
        stories_found: int = 0,
    ) -> None:
        """Increment progress counters for a state.

        Args:
            state_type: Either 'backfill' or 'continuous'
            items_processed: Number of items scanned in this batch
            stories_found: Number of new stories found in this batch
        """
        state = await self.get_state(state_type)
        if state:
            state.items_processed += items_processed
            state.stories_found += stories_found
            state.last_run_at = datetime.now(timezone.utc)
            await self.session.flush()

    async def get_existing_hn_ids(self, hn_ids: list[int]) -> set[int]:
        """Check which HN IDs already exist in the database.

        This is the key optimization - check before fetching full content.
        Single query to check hundreds of IDs at once.
        For large lists (>1000), chunks the query to avoid slow IN clauses.

        Args:
            hn_ids: List of HN item IDs to check

        Returns:
            Set of hn_ids that already exist in the stories table
        """
        if not hn_ids:
            return set()

        # For small lists, use a single query
        if len(hn_ids) <= 1000:
            stmt = select(StoryModel.hn_id).where(StoryModel.hn_id.in_(hn_ids))
            result = await self.session.execute(stmt)
            return set(row[0] for row in result.all())

        # For large lists, chunk to avoid slow IN clauses
        chunk_size = 1000
        existing_ids = set()

        for i in range(0, len(hn_ids), chunk_size):
            chunk = hn_ids[i:i + chunk_size]
            stmt = select(StoryModel.hn_id).where(StoryModel.hn_id.in_(chunk))
            result = await self.session.execute(stmt)
            existing_ids.update(row[0] for row in result.all())

        return existing_ids

    async def get_max_hn_id(self) -> int | None:
        """Get the maximum HN ID in our database.

        Returns:
            The highest hn_id stored, or None if no stories exist
        """
        stmt = select(func.max(StoryModel.hn_id))
        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_min_hn_id(self) -> int | None:
        """Get the minimum HN ID in our database.

        Returns:
            The lowest hn_id stored, or None if no stories exist
        """
        stmt = select(func.min(StoryModel.hn_id))
        result = await self.session.execute(stmt)
        return result.scalar()

    async def get_story_count(self) -> int:
        """Get total number of stories in database.

        Returns:
            Total count of stories
        """
        stmt = select(func.count(StoryModel.id))
        result = await self.session.execute(stmt)
        return result.scalar() or 0
