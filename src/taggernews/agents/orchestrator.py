"""Agent Orchestrator for coordinating the agent workflow."""

import logging
from typing import Any, Literal

from taggernews.agents.tag_proposer import TagProposerAgent
from taggernews.agents.tag_reorganizer import TagReorganizerAgent
from taggernews.agents.taxonomy_analyzer import TaxonomyAnalyzerAgent
from taggernews.config import get_settings
from taggernews.infrastructure.database import async_session_factory
from taggernews.infrastructure.models import TagProposalModel
from taggernews.repositories.agent_repo import AgentRepository

logger = logging.getLogger(__name__)
settings = get_settings()

RunMode = Literal["analysis", "proposal", "auto-apply"]


class AgentOrchestrator:
    """Coordinates the agent workflow.

    Workflow modes:
    - 'analysis': Run analyzer only, store results
    - 'proposal': Run analyzer + proposer, create pending proposals
    - 'auto-apply': Run full pipeline, auto-approve low-risk proposals
    """

    async def run_analysis_pipeline(self, mode: RunMode = "proposal") -> dict[str, Any]:
        """Run the full agent pipeline.

        Args:
            mode: Pipeline mode ('analysis', 'proposal', 'auto-apply')

        Returns:
            Pipeline result with run_id and statistics
        """
        logger.info(f"Starting agent pipeline in '{mode}' mode")

        async with async_session_factory() as session:
            agent_repo = AgentRepository(session)

            # Create run record
            run = await agent_repo.create_run(run_type=mode)

            try:
                # Step 1: Analyze taxonomy
                logger.info("Step 1: Running taxonomy analysis...")
                analyzer = TaxonomyAnalyzerAgent(session)
                analysis = await analyzer.run({})

                if mode == "analysis":
                    await agent_repo.complete_run(run.id, {"analysis": analysis})
                    await session.commit()
                    return {
                        "run_id": run.id,
                        "mode": mode,
                        "analysis": analysis,
                    }

                # Step 2: Generate proposals
                logger.info("Step 2: Generating proposals...")
                proposer = TagProposerAgent(session)
                proposer_result = await proposer.run({"analysis": analysis})

                proposals_data = proposer_result.get("proposals", [])

                # Step 3: Store proposals in database
                logger.info(f"Step 3: Storing {len(proposals_data)} proposals...")
                proposal_ids = []
                for p in proposals_data:
                    db_proposal = await agent_repo.create_proposal(
                        agent_run_id=run.id,
                        proposal_type=p["proposal_type"],
                        reason=p["reason"],
                        data=p["data"],
                        affected_count=p.get("affected_stories_count", 0),
                        priority=p.get("priority", "medium"),
                    )
                    proposal_ids.append(db_proposal.id)

                # Step 4: Auto-approve if enabled and low-risk
                auto_approved = []
                if mode == "auto-apply" and settings.agent_enable_auto_approve:
                    logger.info("Step 4: Auto-approving low-risk proposals...")
                    for proposal_id in proposal_ids:
                        proposal = await agent_repo.get_proposal(proposal_id)
                        if proposal and self._is_low_risk(proposal):
                            await agent_repo.approve_proposal(
                                proposal_id, "auto-approver"
                            )
                            auto_approved.append(proposal_id)
                            logger.info(f"Auto-approved proposal {proposal_id}")

                # Complete the run
                await agent_repo.complete_run(
                    run.id,
                    {
                        "analysis": analysis,
                        "proposals_created": len(proposal_ids),
                        "auto_approved": len(auto_approved),
                        "summary": proposer_result.get("summary", ""),
                    },
                )
                await session.commit()

                result = {
                    "run_id": run.id,
                    "mode": mode,
                    "proposals_created": len(proposal_ids),
                    "proposal_ids": proposal_ids,
                    "auto_approved": len(auto_approved),
                    "summary": proposer_result.get("summary", ""),
                }
                logger.info(f"Pipeline complete: {result}")
                return result

            except Exception as e:
                logger.error(f"Pipeline failed: {e}", exc_info=True)
                await agent_repo.fail_run(run.id, str(e))
                await session.commit()
                raise

    async def execute_proposal(
        self, proposal_id: int, dry_run: bool = False
    ) -> dict[str, Any]:
        """Execute a single approved proposal.

        Args:
            proposal_id: ID of the proposal to execute
            dry_run: If True, only simulate execution

        Returns:
            Execution result
        """
        logger.info(f"Executing proposal {proposal_id} (dry_run={dry_run})")

        async with async_session_factory() as session:
            reorganizer = TagReorganizerAgent(session)
            result = await reorganizer.run({
                "proposal_id": proposal_id,
                "dry_run": dry_run,
            })

            if not dry_run:
                await session.commit()

            return result

    async def execute_all_approved(self, dry_run: bool = False) -> dict[str, Any]:
        """Execute all approved proposals.

        Args:
            dry_run: If True, only simulate execution

        Returns:
            Summary of all executions
        """
        logger.info(f"Executing all approved proposals (dry_run={dry_run})")

        async with async_session_factory() as session:
            agent_repo = AgentRepository(session)
            proposals = await agent_repo.get_proposals(status="approved")

            if not proposals:
                return {"executed": 0, "message": "No approved proposals to execute"}

            results = []
            errors = []

            for proposal in proposals:
                try:
                    reorganizer = TagReorganizerAgent(session)
                    result = await reorganizer.run({
                        "proposal_id": proposal.id,
                        "dry_run": dry_run,
                    })
                    results.append({"proposal_id": proposal.id, "result": result})
                except Exception as e:
                    logger.error(f"Failed to execute proposal {proposal.id}: {e}")
                    errors.append({"proposal_id": proposal.id, "error": str(e)})

            if not dry_run:
                await session.commit()

            return {
                "executed": len(results),
                "failed": len(errors),
                "results": results,
                "errors": errors,
            }

    def _is_low_risk(self, proposal: TagProposalModel) -> bool:
        """Determine if proposal is low-risk for auto-approval.

        Args:
            proposal: The proposal to evaluate

        Returns:
            True if safe to auto-approve
        """
        # Only merge and retire are considered for auto-approval
        if proposal.proposal_type not in ["merge_tags", "retire_tag"]:
            return False

        # Must affect few stories
        if proposal.affected_stories_count > settings.agent_auto_approve_max_affected:
            return False

        # Only low/medium priority
        if proposal.priority not in ["low", "medium"]:
            return False

        return True


# Singleton instance
_orchestrator: AgentOrchestrator | None = None


def get_orchestrator() -> AgentOrchestrator:
    """Get or create the orchestrator singleton."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = AgentOrchestrator()
    return _orchestrator
