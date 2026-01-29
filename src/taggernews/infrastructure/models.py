"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Association table for many-to-many relationship between stories and tags
story_tags = Table(
    "story_tags",
    Base.metadata,
    Column("story_id", Integer, ForeignKey("stories.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)


class StoryModel(Base):
    """SQLAlchemy model for stories table."""

    __tablename__ = "stories"
    __table_args__ = (
        Index("ix_stories_processing_status", "is_tagged", "is_summarized"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hn_id: Mapped[int] = mapped_column(
        Integer, unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    author: Mapped[str] = mapped_column(String(100), nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0)
    hn_created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Processing status flags
    is_tagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_summarized: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Relationship to summary
    summary: Mapped["SummaryModel | None"] = relationship(
        "SummaryModel", back_populates="story", uselist=False
    )

    # Relationship to tags (many-to-many)
    tags: Mapped[list["TagModel"]] = relationship(
        "TagModel", secondary=story_tags, back_populates="stories"
    )


class SummaryModel(Base):
    """SQLAlchemy model for summaries table."""

    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    story_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("stories.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship to story
    story: Mapped["StoryModel"] = relationship("StoryModel", back_populates="summary")


class TagModel(Base):
    """SQLAlchemy model for flat tags with level-based grouping.

    Levels:
        1 = Broad categories (Tech, Business, Science, Society)
        2 = Topics (AI/ML, Web, Python, Startups, etc.)
        3+ = Specific tags (GPT-4, LangChain, YC, etc.)

    Categories (for L2 tags):
        Region, Tech Stacks, Industry, etc.
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_misc: Mapped[bool] = mapped_column(default=False, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship to stories (many-to-many)
    stories: Mapped[list["StoryModel"]] = relationship(
        "StoryModel", secondary=story_tags, back_populates="tags"
    )


class AgentRunModel(Base):
    """SQLAlchemy model for tracking agent execution history.

    Run Types:
        - 'analysis': Taxonomy health analysis
        - 'proposal': Proposal generation run
        - 'execution': Proposal execution run

    Status:
        - 'running': Agent currently executing
        - 'completed': Agent finished successfully
        - 'failed': Agent encountered an error
    """

    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_status", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship to proposals
    proposals: Mapped[list["TagProposalModel"]] = relationship(
        "TagProposalModel", back_populates="agent_run"
    )


class TagProposalModel(Base):
    """SQLAlchemy model for storing tag change proposals.

    Proposal Types:
        - 'create_tag': Create a new L2 tag
        - 'merge_tags': Merge multiple tags into one
        - 'split_tag': Split a tag into multiple tags
        - 'retire_tag': Remove a tag and reassign stories

    Status:
        - 'pending': Awaiting review
        - 'approved': Approved for execution
        - 'rejected': Rejected by reviewer
        - 'executed': Successfully executed

    Priority:
        - 'low': Minor optimization
        - 'medium': Recommended change
        - 'high': Important fix needed
    """

    __tablename__ = "tag_proposals"
    __table_args__ = (
        Index("ix_tag_proposals_status", "status"),
        Index("ix_tag_proposals_agent_run", "agent_run_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    agent_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    proposal_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    priority: Mapped[str] = mapped_column(String(10), default="medium", nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    affected_stories_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship to agent run
    agent_run: Mapped["AgentRunModel"] = relationship(
        "AgentRunModel", back_populates="proposals"
    )
