"""
Models 看板服務 —— 彙總每個監測模型的即時指標（給首頁 6 模型看板）。
"""
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models.event import Event
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.models.release import ReleaseEvent
from api.models.sentiment import Sentiment

_RECENT_DAYS = 7
_SENTIMENT_SHRINK = 3.0  # 小樣本收縮（與 ml.sentiment 一致）


async def get_model_dashboard(session: AsyncSession) -> list[dict]:
    """回傳 6 個模型的彙總指標（依 id 排序）。"""
    cutoff = datetime.now(UTC) - timedelta(days=_RECENT_DAYS)

    models = (await session.execute(select(Model).order_by(Model.id))).scalars().all()

    # 貼文總數 + 近 N 天數（一次 group by）
    post_rows = await session.execute(
        select(
            PostModel.model_id,
            func.count().label("total"),
            func.count().filter(Post.posted_at >= cutoff).label("recent"),
        )
        .join(Post, Post.id == PostModel.post_id)
        .group_by(PostModel.model_id)
    )
    posts = {r.model_id: (r.total, r.recent) for r in post_rows}

    # 發布總數 + 最新發布時間
    rel_rows = await session.execute(
        select(
            ReleaseEvent.model_id,
            func.count().label("total"),
            func.max(ReleaseEvent.published_at).label("latest"),
        ).group_by(ReleaseEvent.model_id)
    )
    releases = {r.model_id: (r.total, r.latest) for r in rel_rows}

    # 近 N 天的討論突增最大 severity（看板用紅點標示）
    spike_rows = await session.execute(
        select(Event.model_id, func.max(Event.score).label("sev"))
        .where(Event.event_type == "discussion_spike", Event.occurred_at >= cutoff)
        .group_by(Event.model_id)
    )
    spikes = {r.model_id: r.sev for r in spike_rows}

    # 口碑指數：信心加權 soft（p_positive - p_negative）+ 小樣本收縮，-100..100
    sent_rows = await session.execute(
        select(
            PostModel.model_id,
            func.count().label("n"),
            func.sum(Sentiment.score * (Sentiment.p_positive - Sentiment.p_negative)).label("num"),
            func.sum(Sentiment.score).label("den"),
        )
        .join(Sentiment, Sentiment.post_id == PostModel.post_id)
        .group_by(PostModel.model_id)
    )
    sentiment: dict[int, int] = {}
    for r in sent_rows:
        if r.den and r.den > 0 and r.n:
            soft = r.num / r.den
            shrunk = soft * r.n / (r.n + _SENTIMENT_SHRINK)
            sentiment[r.model_id] = round(shrunk * 100)

    dashboard = []
    for m in models:
        total, recent = posts.get(m.id, (0, 0))
        rtotal, latest = releases.get(m.id, (0, None))
        dashboard.append({
            "slug": m.slug,
            "name": m.name,
            "company": m.company,
            "role": m.role,
            "posts_total": total,
            "posts_recent": recent,
            "releases_total": rtotal,
            "latest_release_at": latest.isoformat() if latest else None,
            "spike_severity": spikes.get(m.id),
            "sentiment_index": sentiment.get(m.id),
        })
    return dashboard
