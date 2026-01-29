"""Tag Proposer Agent for generating taxonomy change proposals using LLM."""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.agents.base import BaseAgent
from taggernews.agents.taxonomy_analyzer import TaxonomyAnalysis
from taggernews.config import get_settings
from taggernews.services.tag_taxonomy import L1_TAGS, L2_TAG_CATEGORIES

logger = logging.getLogger(__name__)
settings = get_settings()


# --- Pydantic Models for Structured Output ---


class MergeProposal(BaseModel):
    """Proposal to merge multiple tags into one."""

    source_tags: list[str]
    target_tag: str
    reason: str
    priority: str  # 'low', 'medium', 'high'


class CreateTagProposal(BaseModel):
    """Proposal to create a new L2 tag."""

    tag_name: str
    category: str
    reason: str
    priority: str


class RetireTagProposal(BaseModel):
    """Proposal to retire a tag."""

    tag_name: str
    replacement_tag: str | None
    reason: str
    priority: str


class ProposalResponse(BaseModel):
    """Response from LLM with all proposals."""

    merge_proposals: list[MergeProposal] = []
    create_proposals: list[CreateTagProposal] = []
    retire_proposals: list[RetireTagProposal] = []


# --- Internal Data Classes ---


@dataclass
class TagProposal:
    """Internal representation of a proposal."""

    proposal_type: str  # 'create_tag', 'merge_tags', 'retire_tag'
    reason: str
    data: dict
    affected_stories_count: int = 0
    priority: str = "medium"


@dataclass
class ProposerResult:
    """Result from the proposer agent."""

    proposals: list[TagProposal] = field(default_factory=list)
    analysis_summary: str = ""


class TagProposerAgent(BaseAgent):
    """Generates proposals to fix taxonomy problems using LLM.

    Takes analysis results and generates actionable proposals:
    - Merge sparse/duplicate tags
    - Create new L2 tags for orphaned stories
    - Retire underused tags
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize proposer agent."""
        super().__init__(session)
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self.model = settings.agent_openai_model
        self.max_proposals = settings.agent_max_proposals_per_run

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Generate proposals based on analysis results.

        Args:
            context: Must contain 'analysis' key with TaxonomyAnalysis dict

        Returns:
            Dict with 'proposals' list and 'summary'
        """
        analysis_data = context.get("analysis", {})
        if not analysis_data:
            self.logger.warning("No analysis data provided")
            return {"proposals": [], "summary": "No analysis data to process"}

        # Convert dict back to TaxonomyAnalysis if needed
        if isinstance(analysis_data, dict):
            analysis = TaxonomyAnalysis(**analysis_data)
        else:
            analysis = analysis_data

        self.logger.info("Generating proposals from analysis results")

        proposals: list[TagProposal] = []

        # Generate proposals for each problem type
        if analysis.duplicate_candidates:
            duplicate_proposals = await self._propose_duplicate_merges(
                analysis.duplicate_candidates
            )
            proposals.extend(duplicate_proposals)

        if analysis.sparse_tags:
            sparse_proposals = await self._propose_sparse_tag_fixes(
                analysis.sparse_tags
            )
            proposals.extend(sparse_proposals)

        if analysis.bloated_categories:
            bloat_proposals = await self._propose_category_fixes(
                analysis.bloated_categories
            )
            proposals.extend(bloat_proposals)

        # Prioritize and limit proposals
        proposals = self._prioritize_proposals(proposals)
        proposals = proposals[: self.max_proposals]

        summary = self._generate_summary(analysis, proposals)

        self.logger.info(f"Generated {len(proposals)} proposals")

        return {
            "proposals": [self._proposal_to_dict(p) for p in proposals],
            "summary": summary,
        }

    async def _propose_duplicate_merges(
        self, duplicates: list[dict]
    ) -> list[TagProposal]:
        """Generate merge proposals for duplicate tags."""
        if not duplicates:
            return []

        proposals = []
        for dup in duplicates:
            # Merge into the tag with more usage
            if dup["tag1_count"] >= dup["tag2_count"]:
                target = dup["tag1"]
                source = dup["tag2"]
                affected = dup["tag2_count"]
            else:
                target = dup["tag2"]
                source = dup["tag1"]
                affected = dup["tag1_count"]

            proposals.append(
                TagProposal(
                    proposal_type="merge_tags",
                    reason=f"Tags '{source}' and '{target}' are {dup['similarity']:.0%} "
                    f"similar. Merging into '{target}' for consistency.",
                    data={"source_tags": [source], "target_tag": target},
                    affected_stories_count=affected,
                    priority="medium" if dup["similarity"] > 0.9 else "low",
                )
            )

        return proposals

    async def _propose_sparse_tag_fixes(
        self, sparse_tags: list[dict]
    ) -> list[TagProposal]:
        """Use LLM to propose fixes for sparse tags."""
        if not sparse_tags:
            return []

        # Build prompt with context
        prompt = self._build_sparse_tags_prompt(sparse_tags)

        try:
            response = await self.openai.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a taxonomy expert. Analyze tag usage "
                        "and propose consolidations. Be conservative - "
                        "only suggest merges when tags are clearly related.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format=ProposalResponse,
            )

            parsed = response.choices[0].message.parsed
            if not parsed:
                return []

            return self._convert_llm_proposals(parsed)

        except Exception as e:
            self.logger.error(f"LLM proposal generation failed: {e}")
            return []

    async def _propose_category_fixes(
        self, bloated_categories: list[dict]
    ) -> list[TagProposal]:
        """Propose fixes for bloated categories."""
        proposals = []

        for cat in bloated_categories:
            # Flag for review rather than auto-merge
            proposals.append(
                TagProposal(
                    proposal_type="review_category",
                    reason=f"Category '{cat['category']}' has {cat['tag_count']} tags, "
                    f"which exceeds the recommended limit of 15. "
                    f"Consider consolidating similar tags.",
                    data={
                        "category": cat["category"],
                        "tag_count": cat["tag_count"],
                        "tags": cat["tags"][:10],  # Top 10 only
                    },
                    affected_stories_count=sum(t["count"] for t in cat["tags"]),
                    priority="low",
                )
            )

        return proposals

    def _build_sparse_tags_prompt(self, sparse_tags: list[dict]) -> str:
        """Build prompt for LLM to analyze sparse tags."""
        # Get L2 tags for reference
        l2_list = list(L2_TAG_CATEGORIES.keys())

        return f"""Analyze these underused tags and suggest consolidations.

Current L1 Categories: {list(L1_TAGS)}
Current L2 Tags: {l2_list}

Sparse tags (fewer than {settings.agent_min_tag_usage} recent uses):
{json.dumps(sparse_tags[:20], indent=2)}

For each sparse tag, decide if it should be:
1. MERGED into an existing tag (if semantically similar)
2. RETIRED (if too specific or no longer relevant)
3. KEPT (if it serves a unique purpose)

Only propose merges/retirements for tags that clearly overlap with existing ones.
Be conservative - when in doubt, keep the tag.

Return structured proposals."""

    def _convert_llm_proposals(self, parsed: ProposalResponse) -> list[TagProposal]:
        """Convert LLM response to internal proposal format."""
        proposals = []

        for merge in parsed.merge_proposals:
            proposals.append(
                TagProposal(
                    proposal_type="merge_tags",
                    reason=merge.reason,
                    data={
                        "source_tags": merge.source_tags,
                        "target_tag": merge.target_tag,
                    },
                    priority=merge.priority,
                )
            )

        for create in parsed.create_proposals:
            proposals.append(
                TagProposal(
                    proposal_type="create_tag",
                    reason=create.reason,
                    data={"tag_name": create.tag_name, "category": create.category},
                    priority=create.priority,
                )
            )

        for retire in parsed.retire_proposals:
            proposals.append(
                TagProposal(
                    proposal_type="retire_tag",
                    reason=retire.reason,
                    data={
                        "tag_name": retire.tag_name,
                        "replacement_tag": retire.replacement_tag,
                    },
                    priority=retire.priority,
                )
            )

        return proposals

    def _prioritize_proposals(self, proposals: list[TagProposal]) -> list[TagProposal]:
        """Sort proposals by priority and affected count."""
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(
            proposals,
            key=lambda p: (
                priority_order.get(p.priority, 2),
                -p.affected_stories_count,
            ),
        )

    def _proposal_to_dict(self, proposal: TagProposal) -> dict:
        """Convert proposal to dictionary."""
        return {
            "proposal_type": proposal.proposal_type,
            "reason": proposal.reason,
            "data": proposal.data,
            "affected_stories_count": proposal.affected_stories_count,
            "priority": proposal.priority,
        }

    def _generate_summary(
        self, analysis: TaxonomyAnalysis, proposals: list[TagProposal]
    ) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Analyzed {analysis.total_stories_analyzed} stories over "
            f"{analysis.analysis_window_days} days.",
            f"Found {analysis.total_tags} total tags.",
        ]

        if analysis.orphan_stories:
            lines.append(f"- {analysis.orphan_stories} stories missing L1/L2 tags")
        if analysis.duplicate_candidates:
            lines.append(
                f"- {len(analysis.duplicate_candidates)} potential duplicate tag pairs"
            )
        if analysis.sparse_tags:
            lines.append(f"- {len(analysis.sparse_tags)} sparse tags (low usage)")
        if analysis.bloated_categories:
            lines.append(f"- {len(analysis.bloated_categories)} bloated categories")

        lines.append(f"\nGenerated {len(proposals)} proposals for review.")

        return "\n".join(lines)
