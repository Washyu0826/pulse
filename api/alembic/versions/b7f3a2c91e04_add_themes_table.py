"""add themes table

Revision ID: b7f3a2c91e04
Revises: 32a6a15ed0d2
Create Date: 2026-05-31 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7f3a2c91e04"
down_revision: str | None = "32a6a15ed0d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "themes",
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("confident", sa.Boolean(), nullable=False),
        sa.Column(
            "classified_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_themes_post_id_posts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("post_id", name=op.f("pk_themes")),
    )
    op.create_index("ix_themes_label", "themes", ["label"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_themes_label", table_name="themes")
    op.drop_table("themes")
