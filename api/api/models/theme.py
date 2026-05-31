"""
Themes 表 —— 每篇貼文的「主題分類」結果（地端 zero-shot）。

回應使用者需求：除了「講哪個模型 + 情緒」，再標出貼文屬於哪個主題：
邊界（AI 限制/風險）、新工具、使用方法、其他。與 sentiments 正交、各一筆（post_id 主鍵）。
"""
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class Theme(Base, TimestampMixin):
    """單篇貼文的主題分類結果。"""

    __tablename__ = "themes"

    post_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    label: Mapped[str] = mapped_column(Text)  # '邊界' | '新工具' | '使用方法' | '其他'
    confidence: Mapped[float] = mapped_column(Float)  # 該標籤的 zero-shot 分數（0-1）
    confident: Mapped[bool] = mapped_column(Boolean)  # 是否通過信心門檻（否則歸「其他」）
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_themes_label", "label"),)
