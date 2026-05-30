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
from api.services.models import _SENTIMENT_SHRINK, get_model_dashboard

# 趨勢圖預設天數窗口（與看板「近 7 天」不同：趨勢需要更長脈絡才看得出走勢）。
_TREND_DAYS = 30
_TOP_DISCUSSIONS = 5
_RECENT_EVENTS = 8
_LATEST_RELEASES = 5


def _daily_volume(rows) -> dict[date, int]:
    return {r.day: r.n for r in rows}


async def get_model_detail(
    session: AsyncSession, slug: str, trend_days: int = _TREND_DAYS
) -> dict | None:
    """回傳單一模型的完整詳情；查無 slug 回 None。"""
    model = (
        await session.execute(select(Model).where(Model.slug == slug))
    ).scalar_one_or_none()
    if model is None:
        return None

    # 彙總指標：直接從看板取同一筆（口碑/討論量定義一致，single source of truth）。
    dashboard = {d["slug"]: d for d in await get_model_dashboard(session)}
    summary = dashboard.get(slug)

    now = datetime.now(UTC)
    start = now - timedelta(days=trend_days)

    # --- 逐日討論量（依 posted_at 的日期分桶）---
    vol_rows = (
        await session.execute(
            select(
                func.date(Post.posted_at).label("day"),
                func.count().label("n"),
            )
            .join(PostModel, PostModel.post_id == Post.id)
            .where(PostModel.model_id == model.id, Post.posted_at >= start)
            .group_by(func.date(Post.posted_at))
        )
    ).all()
    volume = _daily_volume(vol_rows)

    # --- 逐日口碑指數（信心加權 soft + 小樣本收縮，與看板同公式）---
    sent_rows = (
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
            .where(PostModel.model_id == model.id, Post.posted_at >= start)
            .group_by(func.date(Post.posted_at))
        )
    ).all()
    sentiment_by_day: dict[date, int] = {}
    for r in sent_rows:
        if r.den and r.den > 0 and r.n:
            soft = r.num / r.den
            shrunk = soft * r.n / (r.n + _SENTIMENT_SHRINK)
            sentiment_by_day[r.day] = round(shrunk * 100)

    # 補滿每一天（含 0 討論的日子）→ 前端不必自己補洞，趨勢線連續。
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

    # --- 近期事件 ---
    event_rows = (
        await session.execute(
            select(Event)
            .where(Event.model_id == model.id)
            .order_by(Event.occurred_at.desc(), Event.id.desc())
            .limit(_RECENT_EVENTS)
        )
    ).scalars().all()
    events = [
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
        for ev in event_rows
    ]

    # --- 熱門討論（依分數）---
    disc_rows = (
        await session.execute(
            select(Post.title, Post.score, Post.url, Post.permalink, Post.source)
            .join(PostModel, PostModel.post_id == Post.id)
            .where(PostModel.model_id == model.id)
            .order_by(Post.score.desc())
            .limit(_TOP_DISCUSSIONS)
        )
    ).all()
    top_discussions = [
        {
            "title": r.title,
            "score": r.score,
            "url": r.url or r.permalink,
            "source": r.source,
        }
        for r in disc_rows
    ]

    # --- 最新發布 ---
    rel_rows = (
        await session.execute(
            select(ReleaseEvent)
            .where(ReleaseEvent.model_id == model.id)
            .order_by(ReleaseEvent.published_at.desc())
            .limit(_LATEST_RELEASES)
        )
    ).scalars().all()
    releases = [
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
        for r in rel_rows
    ]

    return {
        "slug": model.slug,
        "name": model.name,
        "company": model.company,
        "role": model.role,
        "posts_total": summary["posts_total"] if summary else 0,
        "posts_recent": summary["posts_recent"] if summary else 0,
        "releases_total": summary["releases_total"] if summary else 0,
        "latest_release_at": summary["latest_release_at"] if summary else None,
        "spike_severity": summary["spike_severity"] if summary else None,
        "sentiment_index": summary["sentiment_index"] if summary else None,
        "trend_days": trend_days,
        "trend": trend,
        "events": events,
        "top_discussions": top_discussions,
        "releases": releases,
    }
