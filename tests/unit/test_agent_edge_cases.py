"""Edge case tests for agent system: proposer, orchestrator, base agent."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from taggernews.agents.base import BaseAgent
from taggernews.agents.orchestrator import AgentOrchestrator, get_orchestrator
from taggernews.agents.tag_proposer import (
    ProposalResponse,
    TagProposal,
    TagProposerAgent,
)
from taggernews.agents.taxonomy_analyzer import TaxonomyAnalysis
from taggernews.infrastructure.models import AgentRunModel, TagProposalModel


class TestBaseAgent:
    """Tests for BaseAgent abstract class."""

    def test_logger_uses_class_name(self):
        """Base agent logger is named after the subclass."""

        class TestAgent(BaseAgent):
            async def run(self, context):
                return {}

        agent = TestAgent(session=AsyncMock())
        assert agent.logger.name == "TestAgent"

    @pytest.mark.asyncio
    async def test_create_run_record_uses_naive_datetime(self):
        """_create_run_record uses datetime.now() (currently naive - known issue)."""
        class TestAgent(BaseAgent):
            async def run(self, context):
                return {}

        mock_session = AsyncMock()
        agent = TestAgent(session=mock_session)

        run = await agent._create_run_record("analysis")

        assert run.run_type == "analysis"
        assert run.status == "running"
        assert isinstance(run.started_at, datetime)
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_run_sets_status(self):
        """_complete_run sets status to completed with result_data."""
        class TestAgent(BaseAgent):
            async def run(self, context):
                return {}

        agent = TestAgent(session=AsyncMock())
        run = AgentRunModel(id=1, run_type="test", status="running", started_at=datetime.now())

        await agent._complete_run(run, {"key": "value"})

        assert run.status == "completed"
        assert run.result_data == {"key": "value"}
        assert run.completed_at is not None

    @pytest.mark.asyncio
    async def test_fail_run_sets_error(self):
        """_fail_run sets status to failed with error message."""
        class TestAgent(BaseAgent):
            async def run(self, context):
                return {}

        agent = TestAgent(session=AsyncMock())
        run = AgentRunModel(id=1, run_type="test", status="running", started_at=datetime.now())

        await agent._fail_run(run, "something broke")

        assert run.status == "failed"
        assert run.error_message == "something broke"


class TestTagProposerEdgeCases:
    """Edge case tests for TagProposerAgent."""

    @pytest.mark.asyncio
    async def test_empty_analysis_returns_no_proposals(self):
        """Returns empty proposals when analysis has no data."""
        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10
            mock_settings.agent_min_tag_usage = 3

            proposer = TagProposerAgent(mock_session)
            result = await proposer.run({"analysis": {}})

        assert result["proposals"] == []

    @pytest.mark.asyncio
    async def test_no_analysis_key_returns_empty(self):
        """Returns empty proposals when context has no 'analysis' key."""
        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10

            proposer = TagProposerAgent(mock_session)
            result = await proposer.run({})

        assert result["proposals"] == []

    def test_prioritize_proposals_order(self):
        """Proposals are sorted by priority then affected count."""
        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10

            proposer = TagProposerAgent(mock_session)

        proposals = [
            TagProposal("merge", "r1", {}, affected_stories_count=5, priority="low"),
            TagProposal("merge", "r2", {}, affected_stories_count=10, priority="high"),
            TagProposal("merge", "r3", {}, affected_stories_count=20, priority="medium"),
            TagProposal("merge", "r4", {}, affected_stories_count=1, priority="high"),
        ]

        sorted_proposals = proposer._prioritize_proposals(proposals)

        # high first (by affected desc), then medium, then low
        assert sorted_proposals[0].priority == "high"
        assert sorted_proposals[0].affected_stories_count == 10
        assert sorted_proposals[1].priority == "high"
        assert sorted_proposals[1].affected_stories_count == 1
        assert sorted_proposals[2].priority == "medium"
        assert sorted_proposals[3].priority == "low"

    def test_generate_summary_with_all_issues(self):
        """Summary includes all issue types when present."""
        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10

            proposer = TagProposerAgent(mock_session)

        analysis = TaxonomyAnalysis(
            orphan_stories=5,
            duplicate_candidates=[{"tag1": "a", "tag2": "b"}],
            sparse_tags=[{"name": "x"}],
            bloated_categories=[{"category": "test"}],
            total_stories_analyzed=100,
            total_tags=50,
            analysis_window_days=30,
        )

        summary = proposer._generate_summary(analysis, [])

        assert "100 stories" in summary
        assert "5 stories missing" in summary
        assert "1 potential duplicate" in summary
        assert "1 sparse" in summary
        assert "1 bloated" in summary

    def test_proposal_to_dict(self):
        """_proposal_to_dict converts all fields correctly."""
        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10

            proposer = TagProposerAgent(mock_session)

        proposal = TagProposal(
            proposal_type="merge_tags",
            reason="Too similar",
            data={"source_tags": ["a"], "target_tag": "b"},
            affected_stories_count=10,
            priority="high",
        )

        d = proposer._proposal_to_dict(proposal)
        assert d["proposal_type"] == "merge_tags"
        assert d["priority"] == "high"
        assert d["affected_stories_count"] == 10

    @pytest.mark.asyncio
    async def test_propose_duplicate_merges_picks_higher_count(self):
        """Merge proposals target the tag with more usage."""
        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10

            proposer = TagProposerAgent(mock_session)

        duplicates = [
            {
                "tag1": "Python", "tag1_count": 5,
                "tag2": "python", "tag2_count": 20,
                "similarity": 0.95,
            },
        ]

        proposals = await proposer._propose_duplicate_merges(duplicates)

        assert len(proposals) == 1
        assert proposals[0].data["target_tag"] == "python"
        assert proposals[0].data["source_tags"] == ["Python"]

    def test_convert_llm_proposals_handles_all_types(self):
        """_convert_llm_proposals converts merge, create, and retire proposals."""
        from taggernews.agents.tag_proposer import (
            CreateTagProposal,
            MergeProposal,
            RetireTagProposal,
        )

        mock_session = AsyncMock()
        with patch("taggernews.agents.tag_proposer.settings") as mock_settings:
            mock_settings.openai_api_key = "test"
            mock_settings.agent_openai_model = "gpt-4o-mini"
            mock_settings.agent_max_proposals_per_run = 10

            proposer = TagProposerAgent(mock_session)

        parsed = ProposalResponse(
            merge_proposals=[MergeProposal(
                source_tags=["a"], target_tag="b", reason="similar", priority="low"
            )],
            create_proposals=[CreateTagProposal(
                tag_name="NewTag", category="Tech Topics", reason="needed", priority="medium"
            )],
            retire_proposals=[RetireTagProposal(
                tag_name="OldTag", replacement_tag="NewTag", reason="outdated", priority="high"
            )],
        )

        proposals = proposer._convert_llm_proposals(parsed)

        assert len(proposals) == 3
        types = [p.proposal_type for p in proposals]
        assert "merge_tags" in types
        assert "create_tag" in types
        assert "retire_tag" in types


class TestOrchestratorEdgeCases:
    """Edge case tests for AgentOrchestrator."""

    def test_is_low_risk_retire_with_low_affected(self):
        """retire_tag is low risk with few affected stories."""
        orch = AgentOrchestrator()
        p = TagProposalModel(
            id=1, agent_run_id=1, proposal_type="retire_tag",
            status="pending", priority="low", reason="test",
            data={}, affected_stories_count=2,
        )
        assert orch._is_low_risk(p) is True

    def test_is_low_risk_split_tag_never(self):
        """split_tag is never low risk."""
        orch = AgentOrchestrator()
        p = TagProposalModel(
            id=1, agent_run_id=1, proposal_type="split_tag",
            status="pending", priority="low", reason="test",
            data={}, affected_stories_count=1,
        )
        assert orch._is_low_risk(p) is False

    def test_is_low_risk_zero_affected(self):
        """Zero affected stories is low risk for merge."""
        orch = AgentOrchestrator()
        p = TagProposalModel(
            id=1, agent_run_id=1, proposal_type="merge_tags",
            status="pending", priority="low", reason="test",
            data={}, affected_stories_count=0,
        )
        assert orch._is_low_risk(p) is True

    def test_get_orchestrator_returns_singleton(self):
        """get_orchestrator returns the same instance on repeated calls."""
        orch1 = get_orchestrator()
        orch2 = get_orchestrator()
        assert orch1 is orch2


class TestTaxonomyAnalysis:
    """Tests for TaxonomyAnalysis dataclass."""

    def test_to_dict_empty(self):
        """Empty analysis converts to dict with zero values."""
        analysis = TaxonomyAnalysis()
        d = analysis.to_dict()
        assert d["orphan_stories"] == 0
        assert d["total_stories_analyzed"] == 0
        assert d["total_tags"] == 0
        assert d["uneven_distribution"] == []
        assert d["sparse_tags"] == []
        assert d["duplicate_candidates"] == []
        assert d["bloated_categories"] == []

    def test_to_dict_populated(self):
        """Populated analysis converts correctly."""
        analysis = TaxonomyAnalysis(
            uneven_distribution=[{"name": "Tech", "percentage": 45.0}],
            orphan_stories=10,
            total_stories_analyzed=500,
            total_tags=100,
        )
        d = analysis.to_dict()
        assert d["orphan_stories"] == 10
        assert len(d["uneven_distribution"]) == 1
        assert d["total_stories_analyzed"] == 500
