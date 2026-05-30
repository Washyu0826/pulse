"""
Sentiments 表 —— 每篇貼文的情緒分析結果（RoBERTa）。

Pulse 與 HN 的差異化落地：每篇討論一筆情緒，聚合成各模型的「口碑指數」，
並支援 sentiment_flip 偵測。一篇貼文一筆（post_id 為主鍵）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class Sentiment(Base, TimestampMixin):
    """單篇貼文的情緒結果。"""

    __tablename__ = "sentiments"

    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    label: Mapped[str] = mapped_column(Text)  # 'positive' | 'neutral' | 'negative'
    score: Mapped[float] = mapped_column(Float)  # 該標籤信心（溫度校準後）
    # 三類機率（保留以便 SQL 端算信心加權 soft 口碑指數 = p_positive - p_negative）
    p_positive: Mapped[float] = mapped_column(Float)
    p_neutral: Mapped[float] = mapped_column(Float)
    p_negative: Mapped[float] = mapped_column(Float)
    confident: Mapped[bool] = mapped_column(Boolean)  # 是否通過信心棄答帶
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_sentiments_label", "label"),)
