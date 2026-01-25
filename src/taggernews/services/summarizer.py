"""OpenAI-powered story summarization service using Response API."""

import logging

from openai import AsyncOpenAI
from pydantic import BaseModel, Field

from taggernews.config import get_settings
from taggernews.domain.story import Story
from taggernews.domain.summary import Summary
from taggernews.services.tag_taxonomy import FlatTags

logger = logging.getLogger(__name__)
settings = get_settings()


class TagsOutput(BaseModel):
    """Flat tag output from LLM."""

    l1_tags: list[str] = Field(
        default_factory=list, description="Broad categories: Tech, Business, Science, Society"
    )
    l2_tags: list[str] = Field(
        default_factory=list, description="Topics: AI/ML, Web, Python, Startups, Security, etc."
    )
    l3_tags: list[str] = Field(
        default_factory=list, description="Specific tags: GPT-4, LangChain, YC, GDPR, etc."
    )


class StoryAnalysis(BaseModel):
    """Structured output for story analysis."""

    summary: str = Field(description="2-3 sentence summary of the story")
    tags: TagsOutput = Field(description="Categorized tags for the story")


SUMMARIZATION_PROMPT = """Analyze this Hacker News story and provide:

1. A concise 2-3 sentence summary
2. Tags organized by level:

**L1 (Broad categories)**: Tech, Business, Science, Society
  - Pick 1-2 that best fit

**L2 (Topics by category)**:
  - Region: EU, USA, China, Canada, India, Germany, France, Netherlands, UK
  - Tech Stacks: Python, Rust, Go, JavaScript, Linux
  - Tech Topics: AI/ML, Web, Systems, Security, Mobile, DevOps, Data, Cloud,
    Open Source, Hardware
  - Business: Startups, Finance, Career, Products, Legal, Marketing
  - Science: Research, Space, Biology, Physics
  - Pick 2-4 relevant topics from any category

**L3 (Specific)**: Use BROAD names for companies/products, not versions.
  Examples: OpenAI (not GPT-4), Google, Meta, AWS, YC, Stripe
  - Pick 0-2 if applicable, only for major entities
  - Avoid version numbers or overly specific terms

Title: {title}
URL: {url}"""


class SummarizerService:
    """Service for generating AI summaries and tags for stories."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """Initialize the summarizer."""
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key)
        self.model = model or settings.summarization_model

    async def summarize_story(self, story: Story) -> tuple[Summary, FlatTags] | None:
        """Generate a summary and flat tags for a story."""
        if not settings.openai_api_key:
            logger.warning("OpenAI API key not configured")
            return None

        try:
            prompt = SUMMARIZATION_PROMPT.format(
                title=story.title,
                url=story.url or "No URL provided",
            )

            response = await self.client.responses.parse(
                model=self.model,
                input=[{"role": "user", "content": prompt}],
                text_format=StoryAnalysis,
            )

            analysis = StoryAnalysis.model_validate_json(response.output_text)

            summary = Summary(
                id=None,
                story_id=story.id or 0,
                text=analysis.summary.strip(),
                model=self.model,
            )

            flat_tags = FlatTags(
                l1_tags=analysis.tags.l1_tags,
                l2_tags=analysis.tags.l2_tags,
                l3_tags=analysis.tags.l3_tags,
            )

            return summary, flat_tags

        except Exception as e:
            logger.error(f"Failed to summarize story {story.hn_id}: {e}")
            return None

    async def summarize_stories(self, stories: list[Story]) -> list[tuple[Summary, FlatTags]]:
        """Generate summaries and tags for multiple stories."""
        results = []
        for story in stories:
            result = await self.summarize_story(story)
            if result:
                results.append(result)

        logger.info(f"Generated {len(results)}/{len(stories)} summaries")
        return results
