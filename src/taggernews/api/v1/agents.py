"""API endpoints for agent management."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict

from taggernews.api.dependencies import AgentRepoDep, OrchestratorDep

router = APIRouter(prefix="/agents", tags=["agents"])


# --- Response Models ---


class ProposalResponse(BaseModel):
    """Response model for tag proposals."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    proposal_type: str
    status: str
    priority: str
    reason: str
    data: dict
    affected_stories_count: int
    created_at: datetime
    reviewed_at: datetime | None
    reviewed_by: str | None
    executed_at: datetime | None


class AgentRunResponse(BaseModel):
    """Response model for agent runs."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_type: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    error_message: str | None
    result_data: dict | None
    created_at: datetime


class RunTriggerResponse(BaseModel):
    """Response from triggering an agent run."""

    run_id: int
    mode: str
    proposals_created: int
    auto_approved: int
    summary: str


class ExecuteResponse(BaseModel):
    """Response from executing a proposal."""

    status: str
    result: dict


# --- Endpoints ---


@router.get("/runs/latest", response_model=AgentRunResponse)
async def get_latest_run(
    agent_repo: AgentRepoDep,
    run_type: str | None = Query(None, pattern="^(analysis|proposal|auto-apply)$"),
) -> AgentRunResponse:
    """Get the most recent agent run."""
    run = await agent_repo.get_latest_run(run_type=run_type)
    if not run:
        raise HTTPException(404, "No agent run found")
    return AgentRunResponse.model_validate(run)


@router.get("/runs", response_model=list[AgentRunResponse])
async def list_runs(
    agent_repo: AgentRepoDep,
    run_type: str | None = Query(None, pattern="^(analysis|proposal|auto-apply)$"),
    status: str | None = Query(None, pattern="^(running|completed|failed)$"),
    limit: int = Query(20, ge=1, le=100),
) -> list[AgentRunResponse]:
    """List agent runs with optional filters."""
    runs = await agent_repo.list_runs(run_type=run_type, status=status, limit=limit)
    return [AgentRunResponse.model_validate(r) for r in runs]


@router.get("/runs/{run_id}", response_model=AgentRunResponse)
async def get_run(run_id: int, agent_repo: AgentRepoDep) -> AgentRunResponse:
    """Get a specific agent run by ID."""
    run = await agent_repo.get_run(run_id)
    if not run:
        raise HTTPException(404, f"Agent run {run_id} not found")
    return AgentRunResponse.model_validate(run)


@router.get("/proposals", response_model=list[ProposalResponse])
async def list_proposals(
    agent_repo: AgentRepoDep,
    status: str | None = Query(
        None, pattern="^(pending|approved|rejected|executed)$"
    ),
    limit: int = Query(50, ge=1, le=200),
) -> list[ProposalResponse]:
    """List tag proposals, optionally filtered by status."""
    proposals = await agent_repo.get_proposals(status=status, limit=limit)
    return [ProposalResponse.model_validate(p) for p in proposals]


@router.get("/proposals/{proposal_id}", response_model=ProposalResponse)
async def get_proposal(
    proposal_id: int, agent_repo: AgentRepoDep
) -> ProposalResponse:
    """Get a specific proposal by ID."""
    proposal = await agent_repo.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_id} not found")
    return ProposalResponse.model_validate(proposal)


@router.post("/proposals/{proposal_id}/approve")
async def approve_proposal(
    proposal_id: int,
    agent_repo: AgentRepoDep,
    reviewer: str = Query("admin"),
) -> dict:
    """Approve a proposal for execution."""
    proposal = await agent_repo.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_id} not found")
    if proposal.status != "pending":
        raise HTTPException(400, f"Proposal is not pending (status: {proposal.status})")

    await agent_repo.approve_proposal(proposal_id, reviewer)
    return {"status": "approved", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: int,
    agent_repo: AgentRepoDep,
    reviewer: str = Query("admin"),
) -> dict:
    """Reject a proposal."""
    proposal = await agent_repo.get_proposal(proposal_id)
    if not proposal:
        raise HTTPException(404, f"Proposal {proposal_id} not found")
    if proposal.status != "pending":
        raise HTTPException(400, f"Proposal is not pending (status: {proposal.status})")

    await agent_repo.reject_proposal(proposal_id, reviewer)
    return {"status": "rejected", "proposal_id": proposal_id}


@router.post("/proposals/{proposal_id}/execute", response_model=ExecuteResponse)
async def execute_proposal(
    proposal_id: int,
    orchestrator: OrchestratorDep,
    dry_run: bool = Query(False),
) -> ExecuteResponse:
    """Execute an approved proposal."""
    try:
        result = await orchestrator.execute_proposal(proposal_id, dry_run)
        status = "dry_run" if dry_run else "executed"
        return ExecuteResponse(status=status, result=result)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/run", response_model=RunTriggerResponse)
async def trigger_agent_run(
    orchestrator: OrchestratorDep,
    mode: str = Query("proposal", pattern="^(analysis|proposal|auto-apply)$"),
) -> RunTriggerResponse:
    """Manually trigger an agent run."""
    result = await orchestrator.run_analysis_pipeline(mode=mode)  # type: ignore
    return RunTriggerResponse(
        run_id=result["run_id"],
        mode=result["mode"],
        proposals_created=result.get("proposals_created", 0),
        auto_approved=result.get("auto_approved", 0),
        summary=result.get("summary", ""),
    )


@router.get("/proposals/pending/count")
async def count_pending_proposals(agent_repo: AgentRepoDep) -> dict:
    """Get the count of pending proposals."""
    count = await agent_repo.count_pending_proposals()
    return {"pending_count": count}
