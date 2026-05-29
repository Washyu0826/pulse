"""
ReleaseEvent 表 — 來自 Hugging Face / GitHub 的「發布訊號」（高精度事件）。

與 posts 不同：這不是討論貼文、沒有情緒，而是「某模型釋出新版本 / 上架」的事件，
直接餵 F8 發布事件偵測（高精度，不需統計推論）。

- source：'huggingface'（模型上架）| 'github'（repo release）
- model_id：對應到哪個監測模型（org/repo → slug 對應，可能 None＝對不到）
- 去重 key = (source, external_id)；HF 用 repo id、GitHub 用 release node_id
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class ReleaseEvent(Base, TimestampMixin):
    """一筆模型發布 / 版本釋出事件。"""

    __tablename__ = "release_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    source: Mapped[str] = mapped_column(Text)  # 'huggingface' | 'github'
    external_id: Mapped[str] = mapped_column(Text)  # HF: repo id；GitHub: release node_id

    # 對應的監測模型（可空：對不到 slug 時保留事件但不關聯）
    model_id: Mapped[int | None] = mapped_column(
        ForeignKey("models.id", ondelete="SET NULL")
    )

    title: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    repo: Mapped[str] = mapped_column(Text)  # HF/GitHub 的 owner/repo 或 repo id
    kind: Mapped[str] = mapped_column(Text)  # 'model_upload' | 'github_release'
    version: Mapped[str | None] = mapped_column(Text)  # GitHub tag；HF 通常 None

    # 事件時間（HF createdAt / GitHub published_at）—— 這是「發布」的時間點
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # 來源特有的額外欄位（downloads/likes/prerelease/body…）
    extra: Mapped[dict] = mapped_column(
        JSONB, server_default=text("'{}'::jsonb"), nullable=False
    )

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("source", "external_id", name="uq_release_events_source_external_id"),
        # 事件流「最近發布」查詢 + 依模型查詢
        Index("ix_release_events_published_at", "published_at"),
        Index("ix_release_events_model_id", "model_id"),
    )
