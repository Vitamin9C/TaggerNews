"""Story domain entity."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Story:
    """Represents a Hacker News story."""

    id: int | None
    hn_id: int
    title: str
    url: str | None
    score: int
    author: str
    comment_count: int
    hn_created_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_hn_api(cls, data: dict) -> "Story":
        """Create Story from HN API response."""
        return cls(
            id=None,
            hn_id=data["id"],
            title=data.get("title", ""),
            url=data.get("url"),
            score=data.get("score", 0),
            author=data.get("by", "unknown"),
            comment_count=data.get("descendants", 0),
            hn_created_at=datetime.fromtimestamp(data.get("time", 0)),
        )
