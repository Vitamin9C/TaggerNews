"""add_tag_category

Revision ID: 8a2f3c4d5e6f
Revises: 7048ce52069b
Create Date: 2026-01-25 03:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8a2f3c4d5e6f"
down_revision: Union[str, None] = "7048ce52069b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Mother categories for L2 tags
L2_TAG_CATEGORIES = {
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
    # Tech Stacks (programming languages already in L2)
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


def upgrade() -> None:
    # Add category column to tags table
    op.add_column("tags", sa.Column("category", sa.String(50), nullable=True))

    # Backfill categories for existing L2 tags
    for tag_name, category in L2_TAG_CATEGORIES.items():
        op.execute(
            f"""
            UPDATE tags
            SET category = '{category}'
            WHERE name = '{tag_name}' AND level = 2
            """
        )


def downgrade() -> None:
    op.drop_column("tags", "category")
