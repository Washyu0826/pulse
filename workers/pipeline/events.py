"""
pipeline.events —— F8 多源事件偵測編排（讀 posts / release_events / sentiments → UPSERT events）。

三類事件：
- discussion_spike：每模型每日討論量做穩健 z-score（median/MAD）偵測突增，主因標題取當日最熱貼文。
- launch：release_events 依 (模型, 日) 聚合（過濾 GitHub prerelease 降噪）。
- sentiment_flip：近 14 天 vs 前 14 天口碑做雙比例 z 檢定。

對帳：刪除「這次未再偵測到」的舊事件（如回填後不再成立的突增），確保 events 表收斂。
冪等：dedup_key 唯一 + 同一交易內 delete+upsert → 重跑安全（適合 Airflow retries）。

只用 ml.sentiment 的純統計 detect_flip（torch 在 SentimentAnalyzer.__init__ 才 import，這裡不載）。
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta

import ml.event_detection as ed
from api.database import AsyncSessionLocal
from api.models.event import Event
from api.models.models import Model, PostModel
from api.models.posts import Post
from api.models.release import ReleaseEvent
from api.models.sentiment import Sentiment
from api.services.events import upsert_events
from ml.sentiment import SentimentAnalyzer, SentimentResult
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_DETECTED_TYPES = ["discussion_spike", "launch", "sentiment_flip"]


def _day_to_dt(d) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


async def _detect_spikes(session: AsyncSession) -> list[dict]:
    post_rows = (
        await session.execute(
            select(Model.slug, Post.posted_at, Post.title, Post.score)
            .join(PostModel, PostModel.post_id == Post.id)
            .join(Model, Model.id == PostModel.model_id)
        )
    ).all()
    by_model: dict[str, list] = defaultdict(list)
    top_post: dict[tuple[str, object], tuple[int, str]] = {}  # (slug, day) -> (score, 主因標題)
    for slug, posted_at, title, score in post_rows:
        day = posted_at.date()
        by_model[slug].append(day)
        key = (slug, day)
        if key not in top_post or (score or 0) > top_post[key][0]:
            top_post[key] = (score or 0, title)

    events = []
    for slug, dates in by_model.items():
        series = ed.fill_daily_gaps(ed.daily_counts(dates))
        for sp in ed.detect_spikes(series):
            cause = top_post.get((slug, sp.day), (0, None))[1]  # 那天最熱門貼文 = 主因
            events.append({
                "dedup_key": f"discussion_spike:{slug}:{sp.day.isoformat()}",
                "event_type": "discussion_spike",
                "model": slug,
                "title": f"{slug} 討論量突增（{sp.count} 篇，平日中位 {sp.median:g}）",
                "description": f"modified z-score {sp.modified_z}（severity {sp.severity}）",
                "score": sp.severity,
                "occurred_at": _day_to_dt(sp.day),
                "extra": {
                    "count": sp.count,
                    "median": sp.median,
                    "modified_z": sp.modified_z,
                    "top_post": cause,
                },
            })
    return events


async def _detect_launches(session: AsyncSession) -> list[dict]:
    rel_rows = (
        await session.execute(
            select(
                Model.slug,
                ReleaseEvent.published_at,
                ReleaseEvent.title,
                ReleaseEvent.kind,
                ReleaseEvent.extra,
            ).join(Model, Model.id == ReleaseEvent.model_id, isouter=True)
        )
    ).all()
    releases = [
        {"model": slug, "day": pub.date(), "title": title, "kind": kind}
        for slug, pub, title, kind, extra in rel_rows
        if not (extra or {}).get("prerelease")  # 降噪：跳過 GitHub prerelease（-rc 等）
    ]
    events = []
    for lc in ed.group_launches(releases):
        events.append({
            "dedup_key": f"launch:{lc.model_slug or '_unknown'}:{lc.day.isoformat()}",
            "event_type": "launch",
            "model": lc.model_slug,
            "title": f"{lc.model_slug or '未知'}：當日 {lc.count} 個發布",
            "description": "；".join(t for t in lc.titles[:3] if t),
            "score": float(lc.count),
            "occurred_at": _day_to_dt(lc.day),
            "extra": {"titles": lc.titles, "count": lc.count, "kinds": lc.kinds},
        })
    return events


async def _detect_flips(session: AsyncSession) -> list[dict]:
    sent_rows = (
        await session.execute(
            select(
                Model.slug,
                Post.posted_at,
                Sentiment.label,
                Sentiment.p_positive,
                Sentiment.p_neutral,
                Sentiment.p_negative,
                Sentiment.score,
            )
            .join(PostModel, PostModel.post_id == Post.id)
            .join(Model, Model.id == PostModel.model_id)
            .join(Sentiment, Sentiment.post_id == Post.id)
        )
    ).all()
    if not sent_rows:
        return []

    max_day = max(r.posted_at for r in sent_rows)
    recent_cut = max_day - timedelta(days=14)
    prior_cut = max_day - timedelta(days=28)
    by_model_period: dict[str, dict[str, list[SentimentResult]]] = defaultdict(
        lambda: {"prev": [], "curr": []}
    )
    for r in sent_rows:
        if r.posted_at < prior_cut:
            continue
        bucket = "curr" if r.posted_at >= recent_cut else "prev"
        res = SentimentResult(
            label=r.label,
            score=r.score,
            scores={"positive": r.p_positive, "neutral": r.p_neutral, "negative": r.p_negative},
        )
        by_model_period[r.slug][bucket].append(res)

    events = []
    for slug, periods in by_model_period.items():
        flip = SentimentAnalyzer.detect_flip(periods["prev"], periods["curr"])
        if not flip.flipped:
            continue
        events.append({
            "dedup_key": f"sentiment_flip:{slug}:{recent_cut.date().isoformat()}",
            "event_type": "sentiment_flip",
            "model": slug,
            "title": f"{slug} 口碑翻轉（{'轉差' if flip.direction == 'to_negative' else '轉好'}）",
            "description": flip.reason,
            "score": round(abs(flip.to_index - flip.from_index)),
            "occurred_at": _day_to_dt(recent_cut.date()),
            "extra": {
                "from_index": flip.from_index,
                "to_index": flip.to_index,
                "direction": flip.direction,
                "z": round(flip.z, 2),
                "p_value": round(flip.p_value, 4),
            },
        })
    return events


async def run_event_detection() -> dict[str, int]:
    """
    執行全部三類事件偵測 + 對帳刪除 + UPSERT，回傳統計。

    回傳：{"discussion_spike", "launch", "sentiment_flip", "received", "upserted", ...}。
    delete + upsert 在同一 session/交易內完成 → 中途失敗不會留下半對帳狀態（retry 安全）。
    """
    async with AsyncSessionLocal() as session:
        spike_events = await _detect_spikes(session)
        launch_events = await _detect_launches(session)
        flip_events = await _detect_flips(session)
        all_events = spike_events + launch_events + flip_events

        # 對帳：刪除這次沒再偵測到的舊事件（如回填後不再成立的突增）。
        current_keys = {e["dedup_key"] for e in all_events}
        if current_keys:
            await session.execute(
                delete(Event).where(
                    Event.event_type.in_(_DETECTED_TYPES),
                    Event.dedup_key.not_in(current_keys),
                )
            )

        stats = await upsert_events(session, all_events)
        # 顯式 commit：upsert_events 在「全部被過濾、無有效列」時會提前 return 不 commit，
        # 那種情況上面的對帳 DELETE 會被 rollback。這裡確保 DELETE 一定落地（正常路徑為 no-op）。
        await session.commit()

    result = {
        "discussion_spike": len(spike_events),
        "launch": len(launch_events),
        "sentiment_flip": len(flip_events),
        **stats,
    }
    logger.info("事件偵測完成：%s", result)
    return result
