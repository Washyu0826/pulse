"""
Posts 表 — 從 Reddit / HackerNews 抓回來的原始貼文。

設計重點：
- 爬蟲只寫 **raw** 資料；DQC（Week 3）之後才填 quality_score / quality_flags（ADR-009）。
- 去重 key = (source, external_id)，UPSERT 用（同一篇被重抓時更新 score / 留言數）。
- 時間戳分三種，不要混淆：
    - posted_at  → 貼文在來源平台的發佈時間（Reddit created_utc）
    - fetched_at → 我們第一次抓到的時間（DQC 找未處理貼文的依據）
    - created_at / updated_at（mixin）→ DB row 稽核時間
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class Post(Base, TimestampMixin):
    """一篇原始貼文。"""

    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # ---- 來源識別 ----
    source: Mapped[str] = mapped_column(Text)  # 'reddit' | 'hackernews'
    external_id: Mapped[str] = mapped_column(Text)  # 來源端原始 id（Reddit 的 t3 id）

    # ---- 內容 ----
    title: Mapped[str] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, server_default=text("''"), nullable=False)
    author: Mapped[str | None] = mapped_column(Text)  # 帳號被刪 = None
    subreddit: Mapped[str | None] = mapped_column(Text)  # HN 來源為 None
    url: Mapped[str | None] = mapped_column(Text)
    permalink: Mapped[str | None] = mapped_column(Text)
    flair: Mapped[str | None] = mapped_column(Text)
    over_18: Mapped[bool] = mapped_column(server_default=text("false"), nullable=False)

    # ---- 互動指標（重抓時會更新）----
    score: Mapped[int] = mapped_column(server_default=text("0"), nullable=False)
    num_comments: Mapped[int] = mapped_column(server_default=text("0"), nullable=False)

    # ---- 時間 ----
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # ---- DQC（v4，Week 3 由 data_quality pipeline 填，ADR-009）----
    quality_score: Mapped[int | None] = mapped_column()  # NULL = 尚未檢核
    quality_flags: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]"), nullable=False
    )
    dq_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_posts_source_external_id"),
        # DQC 依品質分數查詢 / 彙總
        Index("ix_posts_quality_score", "quality_score"),
        # DQC 找「尚未處理」的貼文（partial index，ADR-009）
        Index(
            "ix_posts_dq_unprocessed",
            "fetched_at",
            postgresql_where=text("dq_processed_at IS NULL"),
        ),
        # 時間範圍查詢（自訂查詢 F3 會用）
        Index("ix_posts_posted_at", "posted_at"),
    )
