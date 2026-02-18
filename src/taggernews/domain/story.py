"""Story domain entity."""

from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlparse


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

    @staticmethod
    def _sanitize_url(url: str | None) -> str | None:
        """Reject non-HTTP(S) URLs to prevent javascript: XSS."""
        if not url:
            return None
        scheme = urlparse(url).scheme.lower()
        if scheme in ("http", "https"):
            return url
        return None

    @classmethod
    def from_hn_api(cls, data: dict) -> "Story":
        """Create Story from HN API response."""
        return cls(
            id=None,
            hn_id=data["id"],
            title=data.get("title", ""),
            url=cls._sanitize_url(data.get("url")),
            score=data.get("score", 0),
            author=data.get("by", "unknown"),
            comment_count=data.get("descendants", 0),
            hn_created_at=datetime.fromtimestamp(data.get("time", 0), tz=UTC),
        )
