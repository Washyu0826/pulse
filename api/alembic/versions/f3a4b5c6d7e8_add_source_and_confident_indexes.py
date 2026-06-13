"""add posts.source and themes.confident indexes

Revision ID: f3a4b5c6d7e8
Revises: e1f2a3b4c5d6
Create Date: 2026-06-13 00:00:00.000000

手寫 migration（非 autogenerate）：補兩個查詢熱路徑缺的索引。
- ix_posts_source：corpus 服務 / metrics 的 source 篩選與 GROUP BY 會用（services/corpus.py）。
- ix_themes_confident：feed 服務只取高信心主題（WHERE confident IS TRUE，services/feed.py）。
與 api/models/posts.py、api/models/theme.py 的 Index() 宣告保持一致。
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3a4b5c6d7e8"
down_revision: str | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_posts_source", "posts", ["source"], unique=False)
    op.create_index("ix_themes_confident", "themes", ["confident"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_themes_confident", table_name="themes")
    op.drop_index("ix_posts_source", table_name="posts")
