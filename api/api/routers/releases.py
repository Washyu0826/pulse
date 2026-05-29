"""發布事件 endpoint — F8 發布偵測的高精度訊號面（HF / GitHub）。"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.models.models import Model
from api.models.release import ReleaseEvent

router = APIRouter()


@router.get("/releases/recent")
async def recent_releases(
    limit: int = Query(20, ge=1, le=100),
    source: Literal["huggingface", "github"] | None = Query(None, description="篩選來源"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """最近的發布事件（依 published_at 由新到舊），含對應模型 slug。"""
    stmt = (
        select(ReleaseEvent, Model.slug)
        .join(Model, Model.id == ReleaseEvent.model_id, isouter=True)
        .order_by(ReleaseEvent.published_at.desc())
        .limit(limit)
    )
    if source:
        stmt = stmt.where(ReleaseEvent.source == source)

    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": ev.id,
            "source": ev.source,
            "model": slug,
            "title": ev.title,
            "repo": ev.repo,
            "kind": ev.kind,
            "version": ev.version,
            "url": ev.url,
            "published_at": ev.published_at.isoformat(),
        }
        for ev, slug in rows
    ]
