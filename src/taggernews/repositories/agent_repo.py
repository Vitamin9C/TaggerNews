"""Repository for agent runs and tag proposals."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from taggernews.infrastructure.models import AgentRunModel, TagProposalModel


class AgentRepository:
    """Repository for agent runs and tag proposals."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session."""
        self.session = session

    # --- Agent Run Methods ---

    async def create_run(self, run_type: str) -> AgentRunModel:
        """Create a new agent run record.

        Args:
            run_type: Type of run ('analysis', 'proposal', 'execution')

        Returns:
            Created AgentRunModel instance
        """
        run = AgentRunModel(
            run_type=run_type,
            status="running",
            started_at=datetime.now(),
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def complete_run(self, run_id: int, result_data: dict) -> None:
        """Mark a run as completed with result data.

        Args:
            run_id: ID of the run to complete
            result_data: Results from the run
        """
        stmt = select(AgentRunModel).where(AgentRunModel.id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            run.status = "completed"
            run.completed_at = datetime.now()
            run.result_data = result_data

    async def fail_run(self, run_id: int, error: str) -> None:
        """Mark a run as failed with error message.

        Args:
            run_id: ID of the run to fail
            error: Error message describing the failure
        """
        stmt = select(AgentRunModel).where(AgentRunModel.id == run_id)
        result = await self.session.execute(stmt)
        run = result.scalar_one_or_none()
        if run:
            run.status = "failed"
            run.completed_at = datetime.now()
            run.error_message = error

    async def get_run(self, run_id: int) -> AgentRunModel | None:
        """Get an agent run by ID.

        Args:
            run_id: ID of the run to retrieve

        Returns:
            AgentRunModel or None if not found
        """
        stmt = (
            select(AgentRunModel)
            .options(selectinload(AgentRunModel.proposals))
            .where(AgentRunModel.id == run_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_run(self, run_type: str | None = None) -> AgentRunModel | None:
        """Get the most recent agent run.

        Args:
            run_type: Optional filter by run type

        Returns:
            Most recent AgentRunModel or None
        """
        stmt = (
            select(AgentRunModel)
            .options(selectinload(AgentRunModel.proposals))
            .order_by(AgentRunModel.created_at.desc())
        )
        if run_type:
            stmt = stmt.where(AgentRunModel.run_type == run_type)
        stmt = stmt.limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        run_type: str | None = None,
        status: str | None = None,
        limit: int = 20,
    ) -> list[AgentRunModel]:
        """List agent runs with optional filters.

        Args:
            run_type: Optional filter by run type
            status: Optional filter by status
            limit: Maximum number of runs to return

        Returns:
            List of AgentRunModel instances
        """
        stmt = (
            select(AgentRunModel)
            .options(selectinload(AgentRunModel.proposals))
            .order_by(AgentRunModel.created_at.desc())
        )
        if run_type:
            stmt = stmt.where(AgentRunModel.run_type == run_type)
        if status:
            stmt = stmt.where(AgentRunModel.status == status)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    # --- Tag Proposal Methods ---

    async def create_proposal(
        self,
        agent_run_id: int,
        proposal_type: str,
        reason: str,
        data: dict,
        affected_count: int,
        priority: str = "medium",
    ) -> TagProposalModel:
        """Create a new tag proposal.

        Args:
            agent_run_id: ID of the agent run that created this proposal
            proposal_type: Type of proposal ('create_tag', 'merge_tags', etc.)
            reason: LLM-generated justification
            data: Proposal-specific data (e.g., source_tags, target_tag)
            affected_count: Number of stories affected
            priority: Priority level ('low', 'medium', 'high')

        Returns:
            Created TagProposalModel instance
        """
        proposal = TagProposalModel(
            agent_run_id=agent_run_id,
            proposal_type=proposal_type,
            reason=reason,
            data=data,
            affected_stories_count=affected_count,
            priority=priority,
        )
        self.session.add(proposal)
        await self.session.flush()
        return proposal

    async def get_proposal(self, proposal_id: int) -> TagProposalModel | None:
        """Get a tag proposal by ID.

        Args:
            proposal_id: ID of the proposal to retrieve

        Returns:
            TagProposalModel or None if not found
        """
        stmt = (
            select(TagProposalModel)
            .options(selectinload(TagProposalModel.agent_run))
            .where(TagProposalModel.id == proposal_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_proposals(
        self,
        status: str | None = None,
        limit: int = 50,
    ) -> list[TagProposalModel]:
        """List tag proposals with optional status filter.

        Args:
            status: Optional filter by status ('pending', 'approved', etc.)
            limit: Maximum number of proposals to return

        Returns:
            List of TagProposalModel instances
        """
        stmt = (
            select(TagProposalModel)
            .options(selectinload(TagProposalModel.agent_run))
            .order_by(TagProposalModel.created_at.desc())
        )
        if status:
            stmt = stmt.where(TagProposalModel.status == status)
        stmt = stmt.limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_proposals_by_run(self, agent_run_id: int) -> list[TagProposalModel]:
        """Get all proposals for a specific agent run.

        Args:
            agent_run_id: ID of the agent run

        Returns:
            List of TagProposalModel instances
        """
        stmt = (
            select(TagProposalModel)
            .where(TagProposalModel.agent_run_id == agent_run_id)
            .order_by(TagProposalModel.created_at.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def approve_proposal(self, proposal_id: int, reviewer: str) -> None:
        """Approve a proposal for execution.

        Args:
            proposal_id: ID of the proposal to approve
            reviewer: Name/identifier of the reviewer
        """
        stmt = select(TagProposalModel).where(TagProposalModel.id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()
        if proposal:
            proposal.status = "approved"
            proposal.reviewed_at = datetime.now()
            proposal.reviewed_by = reviewer

    async def reject_proposal(self, proposal_id: int, reviewer: str) -> None:
        """Reject a proposal.

        Args:
            proposal_id: ID of the proposal to reject
            reviewer: Name/identifier of the reviewer
        """
        stmt = select(TagProposalModel).where(TagProposalModel.id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()
        if proposal:
            proposal.status = "rejected"
            proposal.reviewed_at = datetime.now()
            proposal.reviewed_by = reviewer

    async def mark_proposal_executed(self, proposal_id: int) -> None:
        """Mark a proposal as executed.

        Args:
            proposal_id: ID of the proposal to mark as executed
        """
        stmt = select(TagProposalModel).where(TagProposalModel.id == proposal_id)
        result = await self.session.execute(stmt)
        proposal = result.scalar_one_or_none()
        if proposal:
            proposal.status = "executed"
            proposal.executed_at = datetime.now()

    async def count_pending_proposals(self) -> int:
        """Count the number of pending proposals.

        Returns:
            Number of pending proposals
        """
        from sqlalchemy import func

        stmt = select(func.count(TagProposalModel.id)).where(
            TagProposalModel.status == "pending"
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0
