"""
單一模型詳情服務 —— 給前端 `/models/[slug]` 頁面用。

組合四種視角（都來自 Pulse 的真實資料，不是 LLM 空想）：
- 彙總指標（沿用看板的 get_model_dashboard 同一套口碑/討論量定義，避免兩處不一致）。
- 時間序列：逐日討論量 + 逐日口碑指數（畫趨勢圖）。
- 近期事件（discussion_spike / launch / sentiment_flip）。
- 熱門討論 + 最新發布。

回傳 None 代表「查無此模型」（route 轉 404）。
"""
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.models.release import ReleaseEvent
from api.models.sentiment import Sentiment
from api.services.models import _sentiment_index, get_model_summary

# 趨勢圖預設天數窗口（與看板「近 7 天」不同：趨勢需要更長脈絡才看得出走勢）。
_TREND_DAYS = 30
_TOP_DISCUSSIONS = 5
_RECENT_EVENTS = 8
_LATEST_RELEASES = 5


async def _daily_volume(
    session: AsyncSession, model_id: int, start: datetime
) -> dict[date, int]:
    """逐日討論量（依 posted_at 的日期分桶）。"""
    rows = (
        await session.execute(
            select(
                func.date(Post.posted_at).label("day"),
                func.count().label("n"),
            )
            .join(PostModel, PostModel.post_id == Post.id)
            .where(PostModel.model_id == model_id, Post.posted_at >= start)
            .group_by(func.date(Post.posted_at))
        )
    ).all()
    return {r.day: r.n for r in rows}


async def _daily_sentiment(
    session: AsyncSession, model_id: int, start: datetime
) -> dict[date, int]:
    """逐日口碑指數（信心加權 soft + 小樣本收縮，與看板同公式）。"""
    rows = (
        await session.execute(
            select(
                func.date(Post.posted_at).label("day"),
                func.count().label("n"),
                func.sum(
                    Sentiment.score * (Sentiment.p_positive - Sentiment.p_negative)
                ).label("num"),
                func.sum(Sentiment.score).label("den"),
            )
            .join(PostModel, PostModel.post_id == Post.id)
            .join(Sentiment, Sentiment.post_id == Post.id)
            .where(PostModel.model_id == model_id, Post.posted_at >= start)
            .group_by(func.date(Post.posted_at))
        )
    ).all()
    out: dict[date, int] = {}
    for r in rows:
        idx = _sentiment_index(r.num, r.den, r.n)
        if idx is not None:
            out[r.day] = idx
    return out


def _build_trend(
    start: datetime,
    trend_days: int,
    volume: dict[date, int],
    sentiment_by_day: dict[date, int],
) -> list[dict]:
    """補滿每一天（含 0 討論的日子）→ 前端不必自己補洞，趨勢線連續。"""
    trend: list[dict] = []
    for i in range(trend_days + 1):
        d = (start + timedelta(days=i)).date()
        trend.append(
            {
                "date": d.isoformat(),
                "posts": volume.get(d, 0),
                "sentiment_index": sentiment_by_day.get(d),
            }
        )
    return trend


async def _recent_events(session: AsyncSession, model_id: int, slug: str) -> list[dict]:
    """近期事件（discussion_spike / launch / sentiment_flip），最新優先。"""
    rows = (
        await session.execute(
            select(Event)
            .where(Event.model_id == model_id)
            .order_by(Event.occurred_at.desc(), Event.id.desc())
            .limit(_RECENT_EVENTS)
        )
    ).scalars().all()
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
        for ev in rows
    ]


async def _top_discussions(session: AsyncSession, model_id: int) -> list[dict]:
    """熱門討論（依分數）。"""
    rows = (
        await session.execute(
            select(Post.title, Post.score, Post.url, Post.permalink, Post.source)
            .join(PostModel, PostModel.post_id == Post.id)
            .where(PostModel.model_id == model_id)
            .order_by(Post.score.desc())
            .limit(_TOP_DISCUSSIONS)
        )
    ).all()
    return [
        {
            "title": r.title,
            "score": r.score,
            "url": r.url or r.permalink,
            "source": r.source,
        }
        for r in rows
    ]


async def _latest_releases(session: AsyncSession, model_id: int, slug: str) -> list[dict]:
    """最新發布。"""
    rows = (
        await session.execute(
            select(ReleaseEvent)
            .where(ReleaseEvent.model_id == model_id)
            .order_by(ReleaseEvent.published_at.desc())
            .limit(_LATEST_RELEASES)
        )
    ).scalars().all()
    return [
        {
            "id": r.id,
            "source": r.source,
            "model": slug,
            "title": r.title,
            "repo": r.repo,
            "kind": r.kind,
            "version": r.version,
            "url": r.url,
            "published_at": r.published_at.isoformat(),
        }
        for r in rows
    ]


async def get_model_detail(
    session: AsyncSession, slug: str, trend_days: int = _TREND_DAYS
) -> dict | None:
    """回傳單一模型的完整詳情；查無 slug 回 None。"""
    model = (
        await session.execute(select(Model).where(Model.slug == slug))
    ).scalar_one_or_none()
    if model is None:
        return None

    # 彙總指標：直接查本模型那一筆（同看板定義，single source of truth），
    # 不撈整盤 6 模型再過濾，省下 5 個模型的彙總計算。
    summary = await get_model_summary(session, model)

    now = datetime.now(UTC)
    start = now - timedelta(days=trend_days)

    volume = await _daily_volume(session, model.id, start)
    sentiment_by_day = await _daily_sentiment(session, model.id, start)
    trend = _build_trend(start, trend_days, volume, sentiment_by_day)
    events = await _recent_events(session, model.id, slug)
    top_discussions = await _top_discussions(session, model.id)
    releases = await _latest_releases(session, model.id, slug)

    return {
        "slug": model.slug,
        "name": model.name,
        "company": model.company,
        "role": model.role,
        "posts_total": summary["posts_total"],
        "posts_recent": summary["posts_recent"],
        "releases_total": summary["releases_total"],
        "latest_release_at": summary["latest_release_at"],
        "spike_severity": summary["spike_severity"],
        "sentiment_index": summary["sentiment_index"],
        "trend_days": trend_days,
        "trend": trend,
        "events": events,
        "top_discussions": top_discussions,
        "releases": releases,
    }
