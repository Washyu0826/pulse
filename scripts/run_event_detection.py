"""
手動執行 F8 事件偵測：讀 posts / release_events → 偵測 → UPSERT 進 events。

- discussion_spike：每個模型的每日討論量做穩健 z-score（median/MAD）偵測突增。
- launch：release_events 依 (模型, 日) 聚合成發布事件。

可重跑（dedup_key 唯一）。Week 7 會被 Airflow DAG 取代。

用法：cd api && uv run python ../scripts/run_event_detection.py
"""
import asyncio
import sys
from collections import defaultdict
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

import ml.event_detection as ed  # noqa: E402
from api.database import AsyncSessionLocal  # noqa: E402
from api.models.event import Event  # noqa: E402
from api.models.models import Model, PostModel  # noqa: E402
from api.models.posts import Post  # noqa: E402
from api.models.release import ReleaseEvent  # noqa: E402
from api.models.sentiment import Sentiment  # noqa: E402
from api.services.events import upsert_events  # noqa: E402

# 只用純統計 detect_flip / summarize，不載模型（torch 在 __init__ 才 import）
from ml.sentiment import SentimentAnalyzer, SentimentResult  # noqa: E402
from sqlalchemy import delete, select  # noqa: E402


def _day_to_dt(d) -> datetime:
    return datetime.combine(d, time.min, tzinfo=UTC)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        # ---- 1) 討論量突增（posts）----
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

        spike_events = []
        for slug, dates in by_model.items():
            series = ed.fill_daily_gaps(ed.daily_counts(dates))
            for sp in ed.detect_spikes(series):
                cause = top_post.get((slug, sp.day), (0, None))[1]  # 那天最熱門貼文 = 主因
                spike_events.append({
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

        # ---- 2) 發布事件（release_events）----
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
        launch_events = []
        for lc in ed.group_launches(releases):
            launch_events.append({
                "dedup_key": f"launch:{lc.model_slug or '_unknown'}:{lc.day.isoformat()}",
                "event_type": "launch",
                "model": lc.model_slug,
                "title": f"{lc.model_slug or '未知'}：當日 {lc.count} 個發布",
                "description": "；".join(t for t in lc.titles[:3] if t),
                "score": float(lc.count),
                "occurred_at": _day_to_dt(lc.day),
                "extra": {"titles": lc.titles, "count": lc.count, "kinds": lc.kinds},
            })

        # ---- 3) 口碑翻轉（sentiments，近 14 天 vs 前 14 天）----
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

        flip_events = []
        if sent_rows:
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

            for slug, periods in by_model_period.items():
                flip = SentimentAnalyzer.detect_flip(periods["prev"], periods["curr"])
                if not flip.flipped:
                    continue
                flip_events.append({
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

        all_events = spike_events + launch_events + flip_events

        # 對帳：刪除「這次沒再偵測到」的舊 spike/launch 事件（如回填後不再成立的突增）。
        current_keys = {e["dedup_key"] for e in all_events}
        if current_keys:
            await session.execute(
                delete(Event).where(
                    Event.event_type.in_(["discussion_spike", "launch", "sentiment_flip"]),
                    Event.dedup_key.not_in(current_keys),
                )
            )

        stats = await upsert_events(session, all_events)

    print(
        f"🔎 偵測到：discussion_spike {len(spike_events)} 筆、launch {len(launch_events)} 筆、"
        f"sentiment_flip {len(flip_events)} 筆"
    )
    print("💾 UPSERT 統計：", stats)
    if spike_events:
        print("📈 突增事件樣本：")
        for e in sorted(spike_events, key=lambda x: -x["score"])[:8]:
            print(f"   [{e['occurred_at'].date()}] {e['title']}  severity={e['score']}")


if __name__ == "__main__":
    asyncio.run(main())
