"""add_tag_hierarchy

Revision ID: 5bc07c7e0bed
Revises: 24d7020b2ea6
Create Date: 2026-01-24 17:36:12.104630

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5bc07c7e0bed"
down_revision: str | None = "24d7020b2ea6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Initial taxonomy to seed
INITIAL_TAXONOMY = {
    # L1 Domains
    "Tech": {
        "level": 1,
        "children": {
            "Subdomains": [
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
            ],
            "Tech Stacks": [
                "Python",
                "Rust",
                "Go",
                "JavaScript",
                "C++",
                "Java",
                "React",
                "Kubernetes",
                "PostgreSQL",
                "Linux",
            ],
        },
    },
    "Business": {
        "level": 1,
        "children": {
            "Subdomains": [
                "Startups",
                "Finance",
                "Career",
                "Products",
                "Open Source",
                "Legal",
                "Marketing",
            ],
        },
    },
    "Science": {"level": 1, "children": {}},
    "Society": {"level": 1, "children": {}},
    "Meta": {"level": 1, "children": {}},
}


def upgrade() -> None:
    # Step 1: Add new columns with nullable=True first
    op.add_column("tags", sa.Column("slug", sa.String(length=100), nullable=True))
    op.add_column("tags", sa.Column("level", sa.Integer(), nullable=True))
    op.add_column("tags", sa.Column("subdomain", sa.String(length=50), nullable=True))
    op.add_column("tags", sa.Column("parent_id", sa.Integer(), nullable=True))
    op.add_column("tags", sa.Column("is_misc", sa.Boolean(), nullable=True))
    op.add_column("tags", sa.Column("usage_count", sa.Integer(), nullable=True))
    op.add_column(
        "tags",
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=True),
    )

    # Step 2: Migrate existing tags to L3 misc
    op.execute("""
        UPDATE tags 
        SET slug = LOWER(REPLACE(name, ' ', '-')),
            level = 3,
            is_misc = true,
            usage_count = 0
        WHERE slug IS NULL
    """)

    # Step 3: Make columns NOT NULL after data migration
    op.alter_column("tags", "slug", nullable=False)
    op.alter_column("tags", "level", nullable=False, server_default="3")
    op.alter_column("tags", "is_misc", nullable=False, server_default="false")
    op.alter_column("tags", "usage_count", nullable=False, server_default="0")
    op.alter_column("tags", "created_at", nullable=False)

    # Step 4: Alter name column type
    op.alter_column(
        "tags",
        "name",
        existing_type=sa.VARCHAR(length=50),
        type_=sa.String(length=100),
        existing_nullable=False,
    )

    # Step 5: Update indexes
    op.drop_index(op.f("ix_tags_name"), table_name="tags")
    op.create_index(op.f("ix_tags_slug"), "tags", ["slug"], unique=False)

    # Step 6: Add foreign key
    op.create_foreign_key(
        "fk_tags_parent", "tags", "tags", ["parent_id"], ["id"], ondelete="SET NULL"
    )

    # Step 7: Seed initial taxonomy
    conn = op.get_bind()

    for domain_name, domain_data in INITIAL_TAXONOMY.items():
        # Insert L1 domain
        domain_slug = domain_name.lower().replace(" ", "-")
        result = conn.execute(
            sa.text("""
            INSERT INTO tags (name, slug, level, is_misc, usage_count)
            VALUES (:name, :slug, 1, false, 0)
            ON CONFLICT DO NOTHING
            RETURNING id
        """),
            {"name": domain_name, "slug": domain_slug},
        )
        row = result.fetchone()
        if row:
            domain_id = row[0]
        else:
            # Already exists, get id
            result = conn.execute(
                sa.text("SELECT id FROM tags WHERE slug = :slug"), {"slug": domain_slug}
            )
            domain_id = result.fetchone()[0]

        # Insert L2 children
        for subdomain_name, tags in domain_data.get("children", {}).items():
            for tag_name in tags:
                tag_slug = tag_name.lower().replace(" ", "-").replace("/", "-")
                conn.execute(
                    sa.text("""
                    INSERT INTO tags (name, slug, level, subdomain, parent_id, 
                                      is_misc, usage_count)
                    VALUES (:name, :slug, 2, :subdomain, :parent_id, false, 0)
                    ON CONFLICT DO NOTHING
                """),
                    {
                        "name": tag_name,
                        "slug": tag_slug,
                        "subdomain": subdomain_name,
                        "parent_id": domain_id,
                    },
                )


def downgrade() -> None:
    # Remove foreign key
    op.drop_constraint("fk_tags_parent", "tags", type_="foreignkey")

    # Restore indexes
    op.drop_index(op.f("ix_tags_slug"), table_name="tags")
    op.create_index(op.f("ix_tags_name"), "tags", ["name"], unique=True)

    # Restore name column type
    op.alter_column(
        "tags",
        "name",
        existing_type=sa.String(length=100),
        type_=sa.VARCHAR(length=50),
        existing_nullable=False,
    )

    # Remove new columns
    op.drop_column("tags", "created_at")
    op.drop_column("tags", "usage_count")
    op.drop_column("tags", "is_misc")
    op.drop_column("tags", "parent_id")
    op.drop_column("tags", "subdomain")
    op.drop_column("tags", "level")
    op.drop_column("tags", "slug")

    # ### end Alembic commands ###
