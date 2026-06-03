"""
每日實用情報 feed endpoint（定位 C 首頁核心）。

以主題為主軸（新工具/使用方法/邊界），模型/情緒/來源/時間為篩選維度。
- GET /api/feed          → 各主題 top N 貼文（首頁三分區 / 主題列表頁）
- GET /api/feed/summary  → 各主題計數（首頁今日摘要列）
"""
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.feed import get_feed, get_feed_summary
from api.services.trending import get_trending

router = APIRouter()

Sentiment = Literal["positive", "neutral", "negative"]
Source = Literal["hackernews", "devto", "lobsters", "threads", "reddit"]
Theme = Literal["新工具", "使用方法", "邊界"]


@router.get("/feed")
async def feed(
    model: str | None = Query(None, description="模型 slug 篩選，如 claude"),
    sentiment: Sentiment | None = Query(None, description="情緒篩選"),
    source: Source | None = Query(None, description="來源篩選"),
    days: int = Query(7, ge=1, le=90, description="時間窗（天）"),
    limit_per_theme: int = Query(6, ge=1, le=50, description="每主題取幾則"),
    theme: Theme | None = Query(None, description="只看單一主題（量加大，給列表頁）"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[dict[str, Any]]]:
    """各實用主題的 top N 貼文（最新優先）。回傳 {主題: [貼文卡]}。"""
    return await get_feed(
        db, model=model, sentiment=sentiment, source=source,
        days=days, limit_per_theme=limit_per_theme, theme=theme,
    )


@router.get("/trending")
async def trending(
    limit: int = Query(15, ge=1, le=50, description="取前幾名熱詞"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """本週熱詞榜（近期 vs 基線的 log-odds 趨勢，由 backfill_keywords 預算）。"""
    return await get_trending(db, limit)


@router.get("/feed/summary")
async def feed_summary(
    model: str | None = Query(None),
    sentiment: Sentiment | None = Query(None),
    source: Source | None = Query(None),
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """各實用主題在篩選下的貼文數（首頁今日摘要列）。"""
    return await get_feed_summary(db, model=model, sentiment=sentiment, source=source, days=days)
