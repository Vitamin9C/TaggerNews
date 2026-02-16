"""Tests for AgentOrchestrator._is_low_risk."""

from taggernews.agents.orchestrator import AgentOrchestrator
from taggernews.infrastructure.models import TagProposalModel


class TestIsLowRisk:
    """Tests for _is_low_risk auto-approval logic."""

    def setup_method(self):
        self.orchestrator = AgentOrchestrator()

    def _make_proposal(
        self,
        proposal_type: str = "merge_tags",
        affected: int = 3,
        priority: str = "low",
    ) -> TagProposalModel:
        return TagProposalModel(
            id=1,
            agent_run_id=1,
            proposal_type=proposal_type,
            status="pending",
            priority=priority,
            reason="test",
            data={},
            affected_stories_count=affected,
        )

    def test_low_risk_merge(self):
        p = self._make_proposal("merge_tags", affected=2, priority="low")
        assert self.orchestrator._is_low_risk(p) is True

    def test_low_risk_retire(self):
        p = self._make_proposal("retire_tag", affected=3, priority="medium")
        assert self.orchestrator._is_low_risk(p) is True

    def test_create_tag_never_low_risk(self):
        p = self._make_proposal("create_tag", affected=1, priority="low")
        assert self.orchestrator._is_low_risk(p) is False

    def test_review_category_never_low_risk(self):
        p = self._make_proposal("review_category", affected=1, priority="low")
        assert self.orchestrator._is_low_risk(p) is False

    def test_high_priority_not_low_risk(self):
        p = self._make_proposal("merge_tags", affected=1, priority="high")
        assert self.orchestrator._is_low_risk(p) is False

    def test_too_many_affected_not_low_risk(self):
        p = self._make_proposal("merge_tags", affected=100, priority="low")
        assert self.orchestrator._is_low_risk(p) is False

    def test_boundary_affected_count(self):
        # Default max is 5
        p = self._make_proposal("merge_tags", affected=5, priority="low")
        assert self.orchestrator._is_low_risk(p) is True

        p = self._make_proposal("merge_tags", affected=6, priority="low")
        assert self.orchestrator._is_low_risk(p) is False
