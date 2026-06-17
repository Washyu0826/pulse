"""
產品洞察 dashboard 端點。

提供前端 dashboard 唯一缺的時序資料：主題分布 / 情緒分布隨時間的趨勢。
其餘資料（今日事件 / 熱詞 / 模型 / 主題摘要）已有既有端點。

- GET /api/dashboard/trends?days=14 → 逐日主題分布 + 逐日情緒分布（升冪、缺日補 0）。
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from api.database import get_db
from api.services.dashboard import get_dashboard_trends

router = APIRouter()


class ThemeTrendPoint(BaseModel):
    """單日主題分布。date + 6 個主題鍵（新工具/模型動態/使用方法/風險限制/倫理法規/其他）。

    主題鍵為中文且固定 6 個，用 extra='allow' 讓動態中文鍵通過，不必逐鍵宣告。
    """

    model_config = ConfigDict(extra="allow")

    date: str


class SentimentTrendPoint(BaseModel):
    """單日情緒分布（三類計數）。"""

    date: str
    positive: int
    neutral: int
    negative: int


class DashboardTrends(BaseModel):
    """dashboard 趨勢回應：主題時序 + 情緒時序，皆為日期升冪、缺日補 0。"""

    theme_trend: list[ThemeTrendPoint]
    sentiment_trend: list[SentimentTrendPoint]


@router.get("/dashboard/trends", response_model=DashboardTrends)
async def dashboard_trends(
    days: int = Query(14, ge=1, le=90, description="時間窗（天），涵蓋最近 days 天"),
    db: AsyncSession = Depends(get_db),
) -> DashboardTrends:
    """逐日主題分布 + 逐日情緒分布（依 posted_at 分組，缺資料的日子補 0）。"""
    trends = await get_dashboard_trends(db, days=days)
    return DashboardTrends(**trends)
