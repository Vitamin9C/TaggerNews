"""Summary domain entity."""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class Summary:
    """Represents an AI-generated story summary."""

    id: int | None
    story_id: int
    text: str
    model: str
    created_at: datetime | None = None
