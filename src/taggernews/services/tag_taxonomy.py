"""Taxonomy service for managing flat tag structure with levels."""

import logging
import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from taggernews.infrastructure.models import TagModel

logger = logging.getLogger(__name__)


# Canonical tags by level
L1_TAGS = {"Tech", "Business", "Science", "Society"}

# L2 tags organized by mother category
L2_TAG_CATEGORIES: dict[str, str] = {
    # Region
    "EU": "Region",
    "USA": "Region",
    "China": "Region",
    "Canada": "Region",
    "India": "Region",
    "Germany": "Region",
    "France": "Region",
    "Netherlands": "Region",
    "UK": "Region",
    # Tech Stacks (programming languages/frameworks)
    "Python": "Tech Stacks",
    "Rust": "Tech Stacks",
    "Go": "Tech Stacks",
    "JavaScript": "Tech Stacks",
    "Linux": "Tech Stacks",
    # Tech Topics
    "AI/ML": "Tech Topics",
    "Web": "Tech Topics",
    "Systems": "Tech Topics",
    "Security": "Tech Topics",
    "Mobile": "Tech Topics",
    "DevOps": "Tech Topics",
    "Data": "Tech Topics",
    "Cloud": "Tech Topics",
    "Open Source": "Tech Topics",
    "Hardware": "Tech Topics",
    # Business
    "Startups": "Business",
    "Finance": "Business",
    "Career": "Business",
    "Products": "Business",
    "Legal": "Business",
    "Marketing": "Business",
    # Science
    "Research": "Science",
    "Space": "Science",
    "Biology": "Science",
    "Physics": "Science",
}

# Set of all L2 tags for quick lookup
L2_TAGS = set(L2_TAG_CATEGORIES.keys())


def normalize_slug(name: str) -> str:
    """Convert tag name to normalized slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


def get_level_for_tag(name: str) -> int:
    """Determine the level for a tag based on known taxonomy."""
    if name in L1_TAGS:
        return 1
    if name in L2_TAGS:
        return 2
    return 3  # Default to L3 for specific/misc tags


def get_category_for_tag(name: str) -> str | None:
    """Get the mother category for an L2 tag."""
    return L2_TAG_CATEGORIES.get(name)


@dataclass
class FlatTags:
    """Container for flat tags returned by LLM."""

    l1_tags: list[str] = field(default_factory=list)
    l2_tags: list[str] = field(default_factory=list)
    l3_tags: list[str] = field(default_factory=list)

    def all_tags(self) -> list[str]:
        """Get all tags as flat list."""
        return self.l1_tags + self.l2_tags + self.l3_tags


class TaxonomyService:
    """Service for managing flat tags with levels."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialize taxonomy service."""
        self.session = session
        self._tag_cache: dict[str, TagModel] = {}

    async def get_or_create_tag(self, name: str) -> TagModel:
        """Get existing tag or create new one with appropriate level.

        Note: usage_count is not incremented here. Actual usage is
        tracked via the story_tags junction table and can be computed
        with a COUNT query when needed.
        """
        slug = normalize_slug(name)

        # Check cache first
        if slug in self._tag_cache:
            return self._tag_cache[slug]

        # Check database
        stmt = select(TagModel).where(TagModel.slug == slug)
        result = await self.session.execute(stmt)
        tag = result.scalar_one_or_none()

        if tag:
            self._tag_cache[slug] = tag
            return tag

        # Create new tag
        level = get_level_for_tag(name)
        is_misc = level == 3
        category = get_category_for_tag(name)

        tag = TagModel(
            name=name,
            slug=slug,
            level=level,
            category=category,
            is_misc=is_misc,
            usage_count=1,
        )
        self.session.add(tag)
        await self.session.flush()

        self._tag_cache[slug] = tag
        logger.info(f"Created new L{level} tag: {name} (category: {category})")
        return tag

    async def resolve_tags(self, flat_tags: FlatTags) -> list[TagModel]:
        """Resolve FlatTags to TagModel instances."""
        result: list[TagModel] = []
        seen_slugs: set[str] = set()

        for tag_name in flat_tags.all_tags():
            slug = normalize_slug(tag_name)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            tag = await self.get_or_create_tag(tag_name)
            result.append(tag)

        return result

    async def get_tags_by_level(self, level: int) -> list[TagModel]:
        """Get all tags of a specific level."""
        stmt = select(TagModel).where(TagModel.level == level).order_by(TagModel.usage_count.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
