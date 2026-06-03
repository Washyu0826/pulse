"""add trending_keywords table

Revision ID: c8d1e2f3a4b5
Revises: b7f3a2c91e04
Create Date: 2026-06-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8d1e2f3a4b5"
down_revision: str | None = "b7f3a2c91e04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trending_keywords",
        sa.Column("term", sa.Text(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("z", sa.Float(), nullable=False),
        sa.Column("recent_count", sa.Integer(), nullable=False),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("term", name=op.f("pk_trending_keywords")),
    )


def downgrade() -> None:
    op.drop_table("trending_keywords")
