"""事件流 endpoint — F8 偵測到的事件（discussion_spike + launch）。"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.event import Event
from api.models.models import Model

router = APIRouter()


@router.get("/events")
async def list_events(
    limit: int = Query(50, ge=1, le=200),
    event_type: Literal["discussion_spike", "launch", "sentiment_flip"] | None = Query(None),
    model: str | None = Query(None, description="模型 slug 篩選"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """最近偵測到的事件（依 occurred_at 由新到舊），含對應模型 slug。"""
    stmt = (
        select(Event, Model.slug)
        .join(Model, Model.id == Event.model_id, isouter=True)
        # id 當 tiebreak：同日事件很多（occurred_at 是日粒度），避免排序/分頁不穩定
        .order_by(Event.occurred_at.desc(), Event.id.desc())
        .limit(limit)
    )
    if event_type:
        stmt = stmt.where(Event.event_type == event_type)
    if model:
        # 在 outer join 上篩 slug：model_id 為 NULL 的事件 slug 為 NULL，會被排除
        # —— 這是刻意的（指定模型時不要無歸屬事件）；不指定時 null-model 事件仍會出現。
        stmt = stmt.where(Model.slug == model)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": ev.id,
            "event_type": ev.event_type,
            "model": slug,
            "title": ev.title,
            "description": ev.description,
            "score": ev.score,
            "occurred_at": ev.occurred_at.isoformat(),
            "extra": ev.extra,
        }
        for ev, slug in rows
    ]
