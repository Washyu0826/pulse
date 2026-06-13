"""決策報告 endpoint（F3/F4）—— 資料驅動的模型比較。"""
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.decide import compare_models

router = APIRouter()


@router.get("/decide")
async def decide(
    models: list[str] = Query(..., description="模型 slug（可重複參數或逗號分隔），例：claude,gpt"),
    topic: str | None = Query(
        None,
        max_length=100,
        description="議題關鍵字（選填），例：coding agent",
    ),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """比較指定模型，回傳資料驅動的決策報告。支援 ?models=a&models=b 或 ?models=a,b。"""
    slugs = [s.strip().lower() for m in models for s in m.split(",") if s.strip()][:6]
    if not slugs:
        raise HTTPException(status_code=400, detail="請至少指定一個模型 slug")
    return await compare_models(db, slugs, topic)
