"""Tag Reorganizer Agent for executing approved tag proposals."""

import logging
from typing import Any

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.agents.base import BaseAgent
from taggernews.infrastructure.models import TagModel, TagProposalModel, story_tags
from taggernews.repositories.agent_repo import AgentRepository
from taggernews.services.tag_taxonomy import get_category_for_tag, normalize_slug

logger = logging.getLogger(__name__)


class TagReorganizerAgent(BaseAgent):
    """Executes approved tag proposals.

    Operations supported:
    - create_tag: Add new L2 tag to taxonomy
    - merge_tags: Reassign stories from source tags to target tag
    - retire_tag: Remove tag, reassign stories to replacement
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize reorganizer agent."""
        super().__init__(session)
        self.agent_repo = AgentRepository(session)

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Execute a single approved proposal.

        Args:
            context: Must contain 'proposal_id' and optionally 'dry_run'

        Returns:
            Execution result with action details
        """
        proposal_id = context.get("proposal_id")
        dry_run = context.get("dry_run", False)

        if not proposal_id:
            raise ValueError("proposal_id is required")

        proposal = await self.agent_repo.get_proposal(proposal_id)
        if not proposal:
            raise ValueError(f"Proposal {proposal_id} not found")

        if proposal.status != "approved":
            raise ValueError(
                f"Proposal {proposal_id} not approved (status: {proposal.status})"
            )

        self.logger.info(
            f"Executing proposal {proposal_id} (type: {proposal.proposal_type}, "
            f"dry_run: {dry_run})"
        )

        # Execute based on type
        if proposal.proposal_type == "merge_tags":
            result = await self._execute_merge(proposal, dry_run)
        elif proposal.proposal_type == "create_tag":
            result = await self._execute_create(proposal, dry_run)
        elif proposal.proposal_type == "retire_tag":
            result = await self._execute_retire(proposal, dry_run)
        else:
            raise ValueError(f"Unknown proposal type: {proposal.proposal_type}")

        # Mark as executed (unless dry run)
        if not dry_run:
            await self.agent_repo.mark_proposal_executed(proposal_id)
            self.logger.info(f"Proposal {proposal_id} executed successfully")

        return result

    async def _execute_merge(
        self, proposal: TagProposalModel, dry_run: bool
    ) -> dict[str, Any]:
        """Merge multiple tags into one.

        Args:
            proposal: The merge proposal with source_tags and target_tag
            dry_run: If True, only report what would happen

        Returns:
            Execution result
        """
        data = proposal.data
        source_tag_names = data.get("source_tags", [])
        target_tag_name = data.get("target_tag")

        if not source_tag_names or not target_tag_name:
            raise ValueError("merge_tags requires source_tags and target_tag")

        # Get or create target tag
        target = await self._get_or_create_tag(target_tag_name)

        # Find source tags
        source_tags = await self._get_tags_by_names(source_tag_names)
        source_ids = [t.id for t in source_tags]

        if not source_ids:
            return {
                "action": "merge",
                "status": "no_sources",
                "message": "No source tags found",
            }

        # Count affected stories
        affected_count = await self._count_stories_with_tags(source_ids)

        if dry_run:
            return {
                "action": "merge",
                "dry_run": True,
                "source_tags": source_tag_names,
                "target_tag": target_tag_name,
                "source_count": len(source_ids),
                "affected_stories": affected_count,
            }

        # Perform the merge
        # 1. Update story_tags to point to target tag
        for source_id in source_ids:
            # First, delete any duplicate entries that would violate unique constraint
            # (stories that already have both source and target tags)
            await self.session.execute(
                delete(story_tags).where(
                    story_tags.c.tag_id == source_id,
                    story_tags.c.story_id.in_(
                        select(story_tags.c.story_id).where(
                            story_tags.c.tag_id == target.id
                        )
                    ),
                )
            )

            # Then update remaining to point to target
            await self.session.execute(
                update(story_tags)
                .where(story_tags.c.tag_id == source_id)
                .values(tag_id=target.id)
            )

        # 2. Delete source tags
        await self.session.execute(
            delete(TagModel).where(TagModel.id.in_(source_ids))
        )

        # 3. Update target usage count
        new_count = await self._count_tag_usage(target.id)
        target.usage_count = new_count

        return {
            "action": "merge",
            "status": "success",
            "merged_tags": source_tag_names,
            "into": target_tag_name,
            "affected_stories": affected_count,
        }

    async def _execute_create(
        self, proposal: TagProposalModel, dry_run: bool
    ) -> dict[str, Any]:
        """Create a new tag.

        Args:
            proposal: The create proposal with tag_name and category
            dry_run: If True, only report what would happen

        Returns:
            Execution result
        """
        data = proposal.data
        tag_name = data.get("tag_name")
        category = data.get("category")

        if not tag_name:
            raise ValueError("create_tag requires tag_name")

        # Check if tag already exists
        existing = await self._get_tag_by_name(tag_name)
        if existing:
            return {
                "action": "create",
                "status": "already_exists",
                "tag_name": tag_name,
            }

        if dry_run:
            return {
                "action": "create",
                "dry_run": True,
                "tag_name": tag_name,
                "category": category,
                "level": 2,
            }

        # Create the tag
        tag = TagModel(
            name=tag_name,
            slug=normalize_slug(tag_name),
            level=2,
            category=category or get_category_for_tag(tag_name),
            is_misc=False,
            usage_count=0,
        )
        self.session.add(tag)
        await self.session.flush()

        return {
            "action": "create",
            "status": "success",
            "tag_id": tag.id,
            "tag_name": tag_name,
            "category": tag.category,
        }

    async def _execute_retire(
        self, proposal: TagProposalModel, dry_run: bool
    ) -> dict[str, Any]:
        """Retire a tag, optionally reassigning to a replacement.

        Args:
            proposal: The retire proposal with tag_name and optional replacement_tag
            dry_run: If True, only report what would happen

        Returns:
            Execution result
        """
        data = proposal.data
        tag_name = data.get("tag_name")
        replacement_name = data.get("replacement_tag")

        if not tag_name:
            raise ValueError("retire_tag requires tag_name")

        # Find the tag to retire
        tag = await self._get_tag_by_name(tag_name)
        if not tag:
            return {
                "action": "retire",
                "status": "not_found",
                "tag_name": tag_name,
            }

        affected_count = await self._count_tag_usage(tag.id)

        if dry_run:
            return {
                "action": "retire",
                "dry_run": True,
                "tag_name": tag_name,
                "replacement_tag": replacement_name,
                "affected_stories": affected_count,
            }

        # If replacement specified, reassign stories
        if replacement_name:
            replacement = await self._get_or_create_tag(replacement_name)

            # Remove duplicates first
            await self.session.execute(
                delete(story_tags).where(
                    story_tags.c.tag_id == tag.id,
                    story_tags.c.story_id.in_(
                        select(story_tags.c.story_id).where(
                            story_tags.c.tag_id == replacement.id
                        )
                    ),
                )
            )

            # Reassign remaining
            await self.session.execute(
                update(story_tags)
                .where(story_tags.c.tag_id == tag.id)
                .values(tag_id=replacement.id)
            )

            # Update replacement usage count
            replacement.usage_count = await self._count_tag_usage(replacement.id)

        # Delete the retired tag
        await self.session.execute(delete(TagModel).where(TagModel.id == tag.id))

        return {
            "action": "retire",
            "status": "success",
            "retired_tag": tag_name,
            "replacement_tag": replacement_name,
            "affected_stories": affected_count,
        }

    # --- Helper Methods ---

    async def _get_tag_by_name(self, name: str) -> TagModel | None:
        """Get a tag by name."""
        slug = normalize_slug(name)
        stmt = select(TagModel).where(TagModel.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_or_create_tag(self, name: str) -> TagModel:
        """Get existing tag or create new one."""
        tag = await self._get_tag_by_name(name)
        if tag:
            return tag

        # Create new tag
        tag = TagModel(
            name=name,
            slug=normalize_slug(name),
            level=2,
            category=get_category_for_tag(name),
            is_misc=False,
            usage_count=0,
        )
        self.session.add(tag)
        await self.session.flush()
        return tag

    async def _get_tags_by_names(self, names: list[str]) -> list[TagModel]:
        """Get multiple tags by name."""
        slugs = [normalize_slug(n) for n in names]
        stmt = select(TagModel).where(TagModel.slug.in_(slugs))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _count_tag_usage(self, tag_id: int) -> int:
        """Count stories using a tag."""
        stmt = select(func.count(story_tags.c.story_id)).where(
            story_tags.c.tag_id == tag_id
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _count_stories_with_tags(self, tag_ids: list[int]) -> int:
        """Count unique stories using any of the given tags."""
        stmt = select(func.count(func.distinct(story_tags.c.story_id))).where(
            story_tags.c.tag_id.in_(tag_ids)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
