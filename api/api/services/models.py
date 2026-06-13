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
from api.services._quality import quality_post_filter

_RECENT_DAYS = 7
_SENTIMENT_SHRINK = 3.0  # 小樣本收縮（與 ml.sentiment 一致）


def _sentiment_index(num: float | None, den: float | None, n: int | None) -> int | None:
    """口碑指數：信心加權 soft（p_positive - p_negative）+ 小樣本收縮 → -100..100 整數。

    num=Σ score·(p_pos-p_neg)、den=Σ score、n=樣本數。den<=0 或無樣本回 None。
    看板與模型詳情共用，避免兩處公式漂移。
    """
    if den and den > 0 and n:
        soft = num / den
        shrunk = soft * n / (n + _SENTIMENT_SHRINK)
        return round(shrunk * 100)
    return None


async def get_model_summary(session: AsyncSession, model: Model) -> dict:
    """單一模型的彙總指標（與看板同定義，但只查這一個 model_id，不撈整盤再過濾）。

    供 model_detail 用：詳情頁只要本模型那一筆，沒必要算 6 模型再丟掉 5 筆。
    口碑/討論量定義與 get_model_dashboard 完全一致（同 quality_post_filter + 同收縮公式）。
    """
    cutoff = datetime.now(UTC) - timedelta(days=_RECENT_DAYS)

    # 貼文總數 + 近 N 天數（只計高品質、非重複）。
    post_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.count().filter(Post.posted_at >= cutoff).label("recent"),
            )
            # 只 SELECT 聚合、無實體欄位 → 須明確指定左側 FROM，否則 .join(Post) 無從推斷
            # （get_model_dashboard 因 SELECT 了 PostModel.model_id 才不需要）。
            .select_from(PostModel)
            .join(Post, Post.id == PostModel.post_id)
            .where(PostModel.model_id == model.id, *quality_post_filter())
        )
    ).one()

    # 發布總數 + 最新發布時間。
    rel_row = (
        await session.execute(
            select(
                func.count().label("total"),
                func.max(ReleaseEvent.published_at).label("latest"),
            ).where(ReleaseEvent.model_id == model.id)
        )
    ).one()

    # 近 N 天討論突增最大 severity。
    spike = (
        await session.execute(
            select(func.max(Event.score)).where(
                Event.model_id == model.id,
                Event.event_type == "discussion_spike",
                Event.occurred_at >= cutoff,
            )
        )
    ).scalar_one()

    # 口碑指數（同看板：信心加權 soft + 小樣本收縮）。
    sent_row = (
        await session.execute(
            select(
                func.count().label("n"),
                func.sum(
                    Sentiment.score * (Sentiment.p_positive - Sentiment.p_negative)
                ).label("num"),
                func.sum(Sentiment.score).label("den"),
            )
            # 同上：SELECT 只有聚合，須明確左側 FROM 才能 join。
            .select_from(PostModel)
            .join(Sentiment, Sentiment.post_id == PostModel.post_id)
            .join(Post, Post.id == PostModel.post_id)
            .where(PostModel.model_id == model.id, *quality_post_filter())
        )
    ).one()

    latest = rel_row.latest
    return {
        "slug": model.slug,
        "name": model.name,
        "company": model.company,
        "role": model.role,
        "posts_total": post_row.total or 0,
        "posts_recent": post_row.recent or 0,
        "releases_total": rel_row.total or 0,
        "latest_release_at": latest.isoformat() if latest else None,
        "spike_severity": spike,
        "sentiment_index": _sentiment_index(sent_row.num, sent_row.den, sent_row.n),
    }


async def get_model_dashboard(session: AsyncSession) -> list[dict]:
    """回傳 6 個模型的彙總指標（依 id 排序）。"""
    cutoff = datetime.now(UTC) - timedelta(days=_RECENT_DAYS)

    models = (await session.execute(select(Model).order_by(Model.id))).scalars().all()

    # 貼文總數 + 近 N 天數（一次 group by）。只計高品質、非重複（DQC 下游門檻）。
    post_rows = await session.execute(
        select(
            PostModel.model_id,
            func.count().label("total"),
            func.count().filter(Post.posted_at >= cutoff).label("recent"),
        )
        .join(Post, Post.id == PostModel.post_id)
        .where(*quality_post_filter())
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

    # 口碑指數：信心加權 soft（p_positive - p_negative）+ 小樣本收縮，-100..100。
    # 同樣只看高品質、非重複的貼文（與看板計數一致）。
    sent_rows = await session.execute(
        select(
            PostModel.model_id,
            func.count().label("n"),
            func.sum(Sentiment.score * (Sentiment.p_positive - Sentiment.p_negative)).label("num"),
            func.sum(Sentiment.score).label("den"),
        )
        .join(Sentiment, Sentiment.post_id == PostModel.post_id)
        .join(Post, Post.id == PostModel.post_id)
        .where(*quality_post_filter())
        .group_by(PostModel.model_id)
    )
    sentiment: dict[int, int] = {}
    for r in sent_rows:
        idx = _sentiment_index(r.num, r.den, r.n)
        if idx is not None:
            sentiment[r.model_id] = idx

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
