"""
Themes 表 —— 每篇貼文的「主題分類」結果（地端 zero-shot）。

回應使用者需求：除了「講哪個模型 + 情緒」，再標出貼文屬於哪個主題：
新工具、模型動態、使用方法、風險限制、倫理法規、其他（與 ml/ml/theme.py 對齊）。
與 sentiments 正交、各一筆（post_id 主鍵）。
注意：DB 仍殘留少量 2026-06 改版前的舊「邊界」標籤，查詢層（services/feed.py）
會把它映射到「風險限制」。
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
    label: Mapped[str] = mapped_column(Text)  # 5 主題 | '其他'（另有 legacy '邊界'，見模組 docstring）
    confidence: Mapped[float] = mapped_column(Float)  # 該標籤的 zero-shot 分數（0-1）
    confident: Mapped[bool] = mapped_column(Boolean)  # 是否通過信心門檻（否則歸「其他」）
    classified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (Index("ix_themes_label", "label"),)
