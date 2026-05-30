"""模型看板 endpoint —— 首頁 6 模型即時看板（F2）+ 單一模型詳情頁。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.model_detail import get_model_detail
from api.services.models import get_model_dashboard

router = APIRouter()


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """6 個監測模型的彙總指標（貼文數、近 7 天、發布數、近期突增）。"""
    return await get_model_dashboard(db)


@router.get("/models/{slug}")
async def model_detail(
    slug: str,
    trend_days: int = Query(30, ge=7, le=90, description="趨勢圖天數窗口"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """單一模型的完整詳情：彙總指標 + 逐日趨勢 + 近期事件 + 熱門討論 + 最新發布。"""
    detail = await get_model_detail(db, slug.strip().lower(), trend_days)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"查無模型 slug={slug}")
    return detail
