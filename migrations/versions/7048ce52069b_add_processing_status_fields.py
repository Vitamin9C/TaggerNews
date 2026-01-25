"""add_processing_status_fields

Revision ID: 7048ce52069b
Revises: f5bfd41656d2
Create Date: 2026-01-25 02:17:18.403548

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "7048ce52069b"
down_revision: Union[str, None] = "f5bfd41656d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns with server defaults first (for existing rows)
    op.add_column(
        "stories",
        sa.Column(
            "is_summarized",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "stories",
        sa.Column(
            "is_tagged", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
    )

    # Backfill: set is_summarized=true for stories that have a summary
    op.execute(
        """
        UPDATE stories
        SET is_summarized = true
        WHERE id IN (SELECT story_id FROM summaries)
        """
    )

    # Backfill: set is_tagged=true for stories that have at least one tag
    op.execute(
        """
        UPDATE stories
        SET is_tagged = true
        WHERE id IN (SELECT DISTINCT story_id FROM story_tags)
        """
    )

    # Create index for efficient querying of unprocessed stories
    op.create_index(
        "ix_stories_processing_status",
        "stories",
        ["is_tagged", "is_summarized"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_stories_processing_status", table_name="stories")
    op.drop_column("stories", "is_tagged")
    op.drop_column("stories", "is_summarized")
