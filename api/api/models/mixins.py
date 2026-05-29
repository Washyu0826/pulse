"""共用的 SQLAlchemy mixin。"""
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """
    Row 層級的稽核時間戳（不是業務時間，業務時間另設欄位如 posted_at）。

    - created_at：row 第一次寫入時間（DB 端 now()）
    - updated_at：row 最後一次被 ORM UPDATE 的時間

    注意：`onupdate` 只在 ORM 發出的 UPDATE 觸發，**UPSERT / bulk UPDATE 不會觸發**，
    那些情境要在 `set_` 裡顯式塞 `updated_at=func.now()`（見 services/posts.py）。
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
