"""
Translations 表 —— 英文貼文的繁中譯文（地端 qwen2.5），給 feed 中英並列用。

只翻英文貼（HN/Dev.to）；中文貼（Threads）無譯文。一篇一列（post_id 主鍵）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class Translation(Base):
    """單篇貼文的繁中譯文。"""

    __tablename__ = "translations"

    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    title_zh: Mapped[str | None] = mapped_column(Text)
    snippet_zh: Mapped[str | None] = mapped_column(Text)
    translated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
