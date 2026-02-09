"""add_scraper_state

Revision ID: a1b2c3d4e5f6
Revises: 9b3d4e5f6a7c
Create Date: 2026-01-29 12:00:00.000000

Note: The revision ID 'a1b2c3d4e5f6' is a placeholder. If this migration
has already been applied to production/staging, DO NOT regenerate the ID.
If this is being used for the first time, consider regenerating with:
    alembic revision --autogenerate -m "add_scraper_state"

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "9b3d4e5f6a7c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scraper_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("state_type", sa.String(20), nullable=False),
        sa.Column("current_item_id", sa.Integer(), nullable=False),
        sa.Column("target_timestamp", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("items_processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stories_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_run_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scraper_state_type", "scraper_state", ["state_type"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_scraper_state_type", table_name="scraper_state")
    op.drop_table("scraper_state")
