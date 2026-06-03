"""
Trending keywords 表 —— 「本週熱詞」快照（每次 backfill 全表替換）。

近期窗 vs 基線窗的 log-odds 趨勢結果（見 ml/keywords.py）。一個詞一列，rank 決定顯示順序。
非歷史表（不需 row 稽核 mixin）——只存「當前」榜單，重算即覆蓋。
"""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base


class TrendingKeyword(Base):
    """單一熱詞（當前快照）。"""

    __tablename__ = "trending_keywords"

    term: Mapped[str] = mapped_column(Text, primary_key=True)  # 繁體顯示用
    rank: Mapped[int] = mapped_column(Integer)  # 1 = 最熱
    z: Mapped[float] = mapped_column(Float)  # log-odds z 分數
    recent_count: Mapped[int] = mapped_column(Integer)  # 近期出現的文章數
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
