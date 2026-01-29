"""Taxonomy Analyzer Agent for analyzing tag health and distribution."""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.agents.base import BaseAgent
from taggernews.config import get_settings
from taggernews.infrastructure.models import StoryModel, TagModel, story_tags

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class TaxonomyAnalysis:
    """Results from taxonomy analysis."""

    # L1 tags with skewed distribution (>30% or <5% of stories)
    uneven_distribution: list[dict] = field(default_factory=list)
    # Number of stories with only L3 tags (missing L1/L2)
    orphan_stories: int = 0
    # L2 categories with >15 tags
    bloated_categories: list[dict] = field(default_factory=list)
    # Tags with usage_count < threshold
    sparse_tags: list[dict] = field(default_factory=list)
    # Potential duplicate tags (high string similarity)
    duplicate_candidates: list[dict] = field(default_factory=list)
    # Summary statistics
    total_stories_analyzed: int = 0
    total_tags: int = 0
    analysis_window_days: int = 30

    def to_dict(self) -> dict[str, Any]:
        """Convert analysis to dictionary."""
        return {
            "uneven_distribution": self.uneven_distribution,
            "orphan_stories": self.orphan_stories,
            "bloated_categories": self.bloated_categories,
            "sparse_tags": self.sparse_tags,
            "duplicate_candidates": self.duplicate_candidates,
            "total_stories_analyzed": self.total_stories_analyzed,
            "total_tags": self.total_tags,
            "analysis_window_days": self.analysis_window_days,
        }


class TaxonomyAnalyzerAgent(BaseAgent):
    """Analyzes tag taxonomy health and identifies problems.

    Metrics analyzed:
    - L1 distribution balance (should be within 5-30% per category)
    - L2 tags per category (alert if >15)
    - Tag usage counts (flag if <3 uses)
    - Story coverage (% with L1, L2, L3 tags)
    - Duplicate detection (Levenshtein distance < 3 or ratio > 0.85)
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize analyzer agent."""
        super().__init__(session)
        self.window_days = settings.agent_analysis_window_days
        self.min_tag_usage = settings.agent_min_tag_usage

    async def run(self, context: dict[str, Any]) -> dict[str, Any]:
        """Run taxonomy analysis.

        Args:
            context: Optional context (currently unused)

        Returns:
            Analysis results as dictionary
        """
        self.logger.info(f"Starting taxonomy analysis (window: {self.window_days} days)")

        # Get tag statistics for the analysis window
        tag_stats = await self._get_tag_statistics()

        # Run all analyses
        uneven = await self._analyze_distribution(tag_stats)
        orphans = await self._find_orphan_stories()
        bloated = await self._find_bloated_categories(tag_stats)
        sparse = await self._find_sparse_tags(tag_stats)
        duplicates = await self._detect_duplicates(tag_stats)

        # Get summary stats
        total_stories = await self._count_stories_in_window()
        total_tags = len(tag_stats)

        analysis = TaxonomyAnalysis(
            uneven_distribution=uneven,
            orphan_stories=orphans,
            bloated_categories=bloated,
            sparse_tags=sparse,
            duplicate_candidates=duplicates,
            total_stories_analyzed=total_stories,
            total_tags=total_tags,
            analysis_window_days=self.window_days,
        )

        self.logger.info(
            f"Analysis complete: {len(uneven)} uneven, {orphans} orphans, "
            f"{len(bloated)} bloated, {len(sparse)} sparse, {len(duplicates)} duplicates"
        )

        return analysis.to_dict()

    async def _get_tag_statistics(self) -> list[dict]:
        """Get tag usage statistics for the analysis window.

        Returns:
            List of dicts with tag info and usage counts
        """
        cutoff_date = datetime.now() - timedelta(days=self.window_days)

        stmt = (
            select(
                TagModel.id,
                TagModel.name,
                TagModel.slug,
                TagModel.level,
                TagModel.category,
                TagModel.usage_count,
                func.count(story_tags.c.story_id).label("recent_count"),
            )
            .outerjoin(story_tags, TagModel.id == story_tags.c.tag_id)
            .outerjoin(
                StoryModel,
                (story_tags.c.story_id == StoryModel.id)
                & (StoryModel.hn_created_at >= cutoff_date),
            )
            .group_by(
                TagModel.id,
                TagModel.name,
                TagModel.slug,
                TagModel.level,
                TagModel.category,
                TagModel.usage_count,
            )
        )

        result = await self.session.execute(stmt)
        rows = result.all()

        return [
            {
                "id": row.id,
                "name": row.name,
                "slug": row.slug,
                "level": row.level,
                "category": row.category,
                "usage_count": row.usage_count,
                "recent_count": row.recent_count or 0,
            }
            for row in rows
        ]

    async def _count_stories_in_window(self) -> int:
        """Count stories in the analysis window."""
        cutoff_date = datetime.now() - timedelta(days=self.window_days)
        stmt = select(func.count(StoryModel.id)).where(
            StoryModel.hn_created_at >= cutoff_date
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _analyze_distribution(self, tag_stats: list[dict]) -> list[dict]:
        """Analyze L1 tag distribution for imbalances.

        Flags tags with >30% or <5% of stories.
        """
        total_stories = await self._count_stories_in_window()
        if total_stories == 0:
            return []

        l1_stats = [t for t in tag_stats if t["level"] == 1]
        uneven = []

        for tag in l1_stats:
            percentage = (tag["recent_count"] / total_stories) * 100
            if percentage > 30 or (percentage < 5 and tag["recent_count"] > 0):
                uneven.append({
                    "name": tag["name"],
                    "count": tag["recent_count"],
                    "percentage": round(percentage, 2),
                    "issue": "overrepresented" if percentage > 30 else "underrepresented",
                })

        return uneven

    async def _find_orphan_stories(self) -> int:
        """Find stories with only L3 tags (missing L1/L2).

        Returns count of orphan stories in the analysis window.
        """
        cutoff_date = datetime.now() - timedelta(days=self.window_days)

        # Stories that have tags but none are L1 or L2
        stmt = text("""
            SELECT COUNT(DISTINCT s.id)
            FROM stories s
            JOIN story_tags st ON s.id = st.story_id
            WHERE s.hn_created_at >= :cutoff
            AND s.id NOT IN (
                SELECT DISTINCT st2.story_id
                FROM story_tags st2
                JOIN tags t ON st2.tag_id = t.id
                WHERE t.level IN (1, 2)
            )
        """)

        result = await self.session.execute(stmt, {"cutoff": cutoff_date})
        return result.scalar() or 0

    async def _find_bloated_categories(self, tag_stats: list[dict]) -> list[dict]:
        """Find L2 categories with too many tags (>15).

        Groups L2 tags by their mother category and flags bloated ones.
        """
        category_counts: dict[str, list[dict]] = {}

        for tag in tag_stats:
            if tag["level"] == 2 and tag["category"]:
                if tag["category"] not in category_counts:
                    category_counts[tag["category"]] = []
                category_counts[tag["category"]].append({
                    "name": tag["name"],
                    "count": tag["recent_count"],
                })

        bloated = []
        for category, tags in category_counts.items():
            if len(tags) > 15:
                bloated.append({
                    "category": category,
                    "tag_count": len(tags),
                    "tags": sorted(tags, key=lambda x: x["count"], reverse=True),
                })

        return bloated

    async def _find_sparse_tags(self, tag_stats: list[dict]) -> list[dict]:
        """Find tags with usage below threshold.

        Returns L2 and L3 tags with recent_count < min_tag_usage.
        """
        sparse = []

        for tag in tag_stats:
            # Only flag L2/L3 tags, L1 tags are canonical
            if tag["level"] >= 2 and tag["recent_count"] < self.min_tag_usage:
                sparse.append({
                    "name": tag["name"],
                    "level": tag["level"],
                    "category": tag["category"],
                    "recent_count": tag["recent_count"],
                    "total_count": tag["usage_count"],
                })

        # Sort by level (L2 first) then by count
        return sorted(sparse, key=lambda x: (x["level"], x["recent_count"]))

    async def _detect_duplicates(self, tag_stats: list[dict]) -> list[dict]:
        """Detect potential duplicate tags using string similarity.

        Uses SequenceMatcher ratio > 0.85 as threshold.
        """
        duplicates = []
        seen_pairs: set[tuple[str, str]] = set()

        # Only check L2/L3 tags
        check_tags = [t for t in tag_stats if t["level"] >= 2]

        for i, tag1 in enumerate(check_tags):
            for tag2 in check_tags[i + 1 :]:
                # Skip if same tag or already checked
                pair = tuple(sorted([tag1["name"], tag2["name"]]))
                if pair in seen_pairs:
                    continue
                seen_pairs.add(pair)

                # Calculate similarity
                ratio = SequenceMatcher(
                    None, tag1["name"].lower(), tag2["name"].lower()
                ).ratio()

                if ratio > 0.85:
                    duplicates.append({
                        "tag1": tag1["name"],
                        "tag1_count": tag1["recent_count"],
                        "tag2": tag2["name"],
                        "tag2_count": tag2["recent_count"],
                        "similarity": round(ratio, 3),
                    })

        # Sort by similarity descending
        return sorted(duplicates, key=lambda x: x["similarity"], reverse=True)
