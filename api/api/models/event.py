"""
Event 表 — F8 偵測到的「事件」（討論量突增 + 發布）。

統一的事件流（F1 首頁 / F8）：
- discussion_spike：對某模型的每日討論量做穩健 z-score（median/MAD）偵測到的突增。
- launch：把 release_events 依 (模型, 日) 聚合成的發布事件。

dedup_key 唯一 → 偵測可重跑（idempotent upsert，不會重複）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class Event(Base, TimestampMixin):
    """一筆偵測到的事件。"""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)

    # 穩定去重鍵，例： "discussion_spike:claude:2026-05-20" / "launch:llama:2026-05-29"
    dedup_key: Mapped[str] = mapped_column(Text, unique=True)
    event_type: Mapped[str] = mapped_column(Text)  # 'discussion_spike' | 'launch'

    model_id: Mapped[int | None] = mapped_column(ForeignKey("models.id", ondelete="SET NULL"))

    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    # 嚴重度 / 量值：spike 為 severity（capped z）；launch 為當日發布數
    score: Mapped[float | None] = mapped_column(Float)

    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # 事件發生日/時

    extra: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"), nullable=False)

    __table_args__ = (
        Index("ix_events_occurred_at", "occurred_at"),
        Index("ix_events_model_id", "model_id"),
        Index("ix_events_event_type", "event_type"),
    )
