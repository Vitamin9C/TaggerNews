"""use timezone-aware timestamps

Revision ID: 08e4a9c567df
Revises: a1b2c3d4e5f6
Create Date: 2026-02-20 09:15:43.375165

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '08e4a9c567df'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # stories
    op.alter_column("stories", "hn_created_at", type_=sa.DateTime(timezone=True))
    op.alter_column("stories", "created_at", type_=sa.DateTime(timezone=True))
    op.alter_column("stories", "updated_at", type_=sa.DateTime(timezone=True))

    # summaries
    op.alter_column("summaries", "created_at", type_=sa.DateTime(timezone=True))

    # tags
    op.alter_column("tags", "created_at", type_=sa.DateTime(timezone=True))

    # agent_runs
    op.alter_column("agent_runs", "started_at", type_=sa.DateTime(timezone=True))
    op.alter_column("agent_runs", "completed_at", type_=sa.DateTime(timezone=True))
    op.alter_column("agent_runs", "created_at", type_=sa.DateTime(timezone=True))

    # tag_proposals
    op.alter_column("tag_proposals", "created_at", type_=sa.DateTime(timezone=True))
    op.alter_column("tag_proposals", "reviewed_at", type_=sa.DateTime(timezone=True))
    op.alter_column("tag_proposals", "executed_at", type_=sa.DateTime(timezone=True))

    # scraper_state
    op.alter_column("scraper_state", "target_timestamp", type_=sa.DateTime(timezone=True))
    op.alter_column("scraper_state", "last_run_at", type_=sa.DateTime(timezone=True))
    op.alter_column("scraper_state", "created_at", type_=sa.DateTime(timezone=True))
    op.alter_column("scraper_state", "updated_at", type_=sa.DateTime(timezone=True))


def downgrade() -> None:
    # scraper_state
    op.alter_column("scraper_state", "updated_at", type_=sa.DateTime(timezone=False))
    op.alter_column("scraper_state", "created_at", type_=sa.DateTime(timezone=False))
    op.alter_column("scraper_state", "last_run_at", type_=sa.DateTime(timezone=False))
    op.alter_column("scraper_state", "target_timestamp", type_=sa.DateTime(timezone=False))

    # tag_proposals
    op.alter_column("tag_proposals", "executed_at", type_=sa.DateTime(timezone=False))
    op.alter_column("tag_proposals", "reviewed_at", type_=sa.DateTime(timezone=False))
    op.alter_column("tag_proposals", "created_at", type_=sa.DateTime(timezone=False))

    # agent_runs
    op.alter_column("agent_runs", "created_at", type_=sa.DateTime(timezone=False))
    op.alter_column("agent_runs", "completed_at", type_=sa.DateTime(timezone=False))
    op.alter_column("agent_runs", "started_at", type_=sa.DateTime(timezone=False))

    # tags
    op.alter_column("tags", "created_at", type_=sa.DateTime(timezone=False))

    # summaries
    op.alter_column("summaries", "created_at", type_=sa.DateTime(timezone=False))

    # stories
    op.alter_column("stories", "updated_at", type_=sa.DateTime(timezone=False))
    op.alter_column("stories", "created_at", type_=sa.DateTime(timezone=False))
    op.alter_column("stories", "hn_created_at", type_=sa.DateTime(timezone=False))
