"""simplify_tags_flat

Revision ID: f5bfd41656d2
Revises: 5bc07c7e0bed
Create Date: 2026-01-24 18:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f5bfd41656d2"
down_revision: str | None = "5bc07c7e0bed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Flat tag taxonomy - L1 (broad), L2 (topics)
L1_TAGS = ["Tech", "Business", "Science", "Society"]
L2_TAGS = [
    # Tech topics
    "AI/ML",
    "Web",
    "Systems",
    "Security",
    "Mobile",
    "DevOps",
    "Data",
    "Cloud",
    "Open Source",
    "Hardware",
    "Python",
    "Rust",
    "Go",
    "JavaScript",
    "Linux",
    # Business topics
    "Startups",
    "Finance",
    "Career",
    "Products",
    "Legal",
    "Marketing",
    # Science topics
    "Research",
    "Space",
    "Biology",
    "Physics",
]


def upgrade() -> None:
    # Step 1: Drop the foreign key constraint
    op.drop_constraint("fk_tags_parent", "tags", type_="foreignkey")

    # Step 2: Drop parent_id and subdomain columns (no longer needed)
    op.drop_column("tags", "parent_id")
    op.drop_column("tags", "subdomain")

    # Step 3: Clear existing tags and re-seed with flat structure
    conn = op.get_bind()

    # Clear all tags first
    conn.execute(sa.text("DELETE FROM story_tags"))
    conn.execute(sa.text("DELETE FROM tags"))

    # Seed L1 tags
    for name in L1_TAGS:
        slug = name.lower().replace(" ", "-").replace("/", "-")
        conn.execute(
            sa.text("""
            INSERT INTO tags (name, slug, level, is_misc, usage_count)
            VALUES (:name, :slug, 1, false, 0)
        """),
            {"name": name, "slug": slug},
        )

    # Seed L2 tags
    for name in L2_TAGS:
        slug = name.lower().replace(" ", "-").replace("/", "-")
        conn.execute(
            sa.text("""
            INSERT INTO tags (name, slug, level, is_misc, usage_count)
            VALUES (:name, :slug, 2, false, 0)
        """),
            {"name": name, "slug": slug},
        )


def downgrade() -> None:
    # Re-add columns
    op.add_column("tags", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column("tags", sa.Column("subdomain", sa.String(50), nullable=True))

    # Re-add foreign key
    op.create_foreign_key(
        "fk_tags_parent", "tags", "tags", ["parent_id"], ["id"], ondelete="SET NULL"
    )
