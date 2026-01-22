"""SQLAlchemy ORM models."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, func
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    hn_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
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
    """

    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    is_misc: Mapped[bool] = mapped_column(default=False, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Relationship to stories (many-to-many)
    stories: Mapped[list["StoryModel"]] = relationship(
        "StoryModel", secondary=story_tags, back_populates="tags"
    )
