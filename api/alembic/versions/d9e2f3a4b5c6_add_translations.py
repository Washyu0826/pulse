"""add translations table

Revision ID: d9e2f3a4b5c6
Revises: c8d1e2f3a4b5
Create Date: 2026-06-03 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d9e2f3a4b5c6"
down_revision: str | None = "c8d1e2f3a4b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "translations",
        sa.Column("post_id", sa.BigInteger(), nullable=False),
        sa.Column("title_zh", sa.Text(), nullable=True),
        sa.Column("snippet_zh", sa.Text(), nullable=True),
        sa.Column(
            "translated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["post_id"], ["posts.id"], name=op.f("fk_translations_post_id_posts"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("post_id", name=op.f("pk_translations")),
    )


def downgrade() -> None:
    op.drop_table("translations")
