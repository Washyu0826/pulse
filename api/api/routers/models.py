"""模型看板 endpoint —— 首頁 6 模型即時看板（F2）。"""
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.models import get_model_dashboard

router = APIRouter()


@router.get("/models")
async def list_models(db: AsyncSession = Depends(get_db)) -> list[dict[str, Any]]:
    """6 個監測模型的彙總指標（貼文數、近 7 天、發布數、近期突增）。"""
    return await get_model_dashboard(db)
