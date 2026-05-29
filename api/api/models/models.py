"""
Models 主表 — Pulse 監測的 AI 模型清單（GPT / Claude / Gemini / Grok / Llama / DeepSeek）。

對應 docs/PROJECT_PLAN.md §4 監測模型清單。Post 與 Model 之間是多對多
（一篇貼文可能同時提到多個模型），用 post_models 關聯表表達。
"""
from sqlalchemy import ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from api.database import Base
from api.models.mixins import TimestampMixin


class Model(Base, TimestampMixin):
    """一個被監測的 AI 模型。"""

    __tablename__ = "models"

    id: Mapped[int] = mapped_column(primary_key=True)

    # slug：穩定的程式用識別碼（gpt / claude / ...），給 API route 與爬蟲關聯用
    slug: Mapped[str] = mapped_column(Text, unique=True)
    # name：顯示名稱（"GPT-5 / ChatGPT"）
    name: Mapped[str] = mapped_column(Text)
    company: Mapped[str] = mapped_column(Text)
    # role：定位描述（"霸主" / "技術派最愛"），可空
    role: Mapped[str | None] = mapped_column(Text)

    # aliases：關鍵字別名，供爬蟲 / DQC 做關聯比對（例：claude → ["claude", "anthropic"]）
    aliases: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'::text[]"), nullable=False
    )

    is_active: Mapped[bool] = mapped_column(server_default=text("true"), nullable=False)


class PostModel(Base):
    """posts ↔ models 多對多關聯表（複合主鍵）。"""

    __tablename__ = "post_models"

    post_id: Mapped[int] = mapped_column(
        ForeignKey("posts.id", ondelete="CASCADE"), primary_key=True
    )
    model_id: Mapped[int] = mapped_column(
        ForeignKey("models.id", ondelete="CASCADE"), primary_key=True
    )

    __table_args__ = (
        # 反向查詢「某模型有哪些貼文」會用到 model_id
        Index("ix_post_models_model_id", "model_id"),
    )
