"""
Prometheus /metrics —— 業務資料量 gauge（給 Grafana「資料量趨勢」用）。

設計：scrape 時即時查業務 DB，用 custom collector 產 gauge（無狀態、每次重算、不留殘存 series）。
趨勢由 Prometheus 定期抓 gauge 自然形成時間序列（pull 模式；長駐服務不該用 Pushgateway）。
查詢都是 count/group by，索引足夠便宜；另加 60s in-process 快取降低高頻 scrape 的 DB 壓力，
資料量極大時可再改 reltuples 估算。
"""
import time
from collections.abc import Iterator

from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import text

from api.database import AsyncSessionLocal
from api.services._quality import QUALITY_HIGH, QUALITY_MIN

router = APIRouter()

# posts_per_model 加上限：避免語料成長後一次回傳過多 series（理論最多 6 監測模型，
# 取 50 留餘裕；超出代表 models 表有非預期暴增，截斷比拖垮 scrape 安全）。
_POSTS_PER_MODEL_LIMIT = 50

# /metrics 計算結果短暫快取：Prometheus 多 target / 高頻 scrape 時，避免每次都重打一輪
# count/group by。60s 內回上次快照（趨勢圖以分鐘為粒度，60s 陳舊無感）。
_CACHE_TTL_S = 60.0
_cache: dict | None = None
_cache_at: float = 0.0


async def _snapshot() -> dict:
    """一次撈齊各業務量（輕量 count / group by）。"""
    async with AsyncSessionLocal() as s:
        total_posts = (await s.execute(text("SELECT count(*) FROM posts"))).scalar_one()
        posts_24h = (
            await s.execute(
                text("SELECT count(*) FROM posts WHERE fetched_at >= now() - interval '24 hours'")
            )
        ).scalar_one()
        posts_by_source = (
            await s.execute(text("SELECT source, count(*) FROM posts GROUP BY source"))
        ).all()
        # 品質分桶（對齊 DQC 門檻常數：>=HIGH 高、>=MIN 中、<MIN 低、NULL 未檢核）
        quality = (
            await s.execute(
                text(
                    "SELECT CASE WHEN quality_score IS NULL THEN 'unchecked' "
                    "WHEN quality_score >= :high THEN 'high' "
                    "WHEN quality_score >= :min THEN 'mid' ELSE 'low' END AS bucket, "
                    "count(*) FROM posts GROUP BY bucket"
                ),
                {"high": QUALITY_HIGH, "min": QUALITY_MIN},
            )
        ).all()
        duplicates = (
            await s.execute(text("SELECT count(*) FROM posts WHERE quality_flags @> '{DUPLICATE}'"))
        ).scalar_one()
        events_by_type = (
            await s.execute(text("SELECT event_type, count(*) FROM events GROUP BY event_type"))
        ).all()
        releases_by_source = (
            await s.execute(text("SELECT source, count(*) FROM release_events GROUP BY source"))
        ).all()
        sentiments_by_label = (
            await s.execute(text("SELECT label, count(*) FROM sentiments GROUP BY label"))
        ).all()
        posts_per_model = (
            await s.execute(
                text(
                    "SELECT m.slug, count(*) AS n FROM post_models pm "
                    "JOIN models m ON m.id = pm.model_id GROUP BY m.slug "
                    "ORDER BY n DESC LIMIT :lim"
                ),
                {"lim": _POSTS_PER_MODEL_LIMIT},
            )
        ).all()
    return {
        "total_posts": total_posts,
        "posts_24h": posts_24h,
        "duplicates": duplicates,
        "posts_by_source": posts_by_source,
        "quality": quality,
        "events_by_type": events_by_type,
        "releases_by_source": releases_by_source,
        "sentiments_by_label": sentiments_by_label,
        "posts_per_model": posts_per_model,
    }


def _registry(d: dict) -> CollectorRegistry:
    reg = CollectorRegistry()

    class _Collector:
        def collect(self) -> Iterator[GaugeMetricFamily]:
            g = GaugeMetricFamily("pulse_posts_total", "Total posts ingested")
            g.add_metric([], d["total_posts"])
            yield g
            g = GaugeMetricFamily("pulse_posts_last_24h", "Posts fetched in last 24h")
            g.add_metric([], d["posts_24h"])
            yield g
            g = GaugeMetricFamily("pulse_posts_duplicate", "Posts flagged as cross-source duplicate")
            g.add_metric([], d["duplicates"])
            yield g
            g = GaugeMetricFamily("pulse_posts_by_source", "Posts by source", labels=["source"])
            for src, n in d["posts_by_source"]:
                g.add_metric([src or "unknown"], n)
            yield g
            g = GaugeMetricFamily("pulse_posts_quality", "Posts by quality bucket", labels=["bucket"])
            for bucket, n in d["quality"]:
                g.add_metric([bucket], n)
            yield g
            g = GaugeMetricFamily("pulse_events_total", "Events by type", labels=["event_type"])
            for et, n in d["events_by_type"]:
                g.add_metric([et], n)
            yield g
            g = GaugeMetricFamily("pulse_releases_total", "Release events by source", labels=["source"])
            for src, n in d["releases_by_source"]:
                g.add_metric([src], n)
            yield g
            g = GaugeMetricFamily("pulse_sentiments_total", "Sentiments by label", labels=["label"])
            for label, n in d["sentiments_by_label"]:
                g.add_metric([label], n)
            yield g
            g = GaugeMetricFamily("pulse_posts_per_model", "Posts mentioning each model", labels=["model"])
            for slug, n in d["posts_per_model"]:
                g.add_metric([slug], n)
            yield g

    reg.register(_Collector())
    return reg


async def _cached_snapshot() -> dict:
    """回傳業務量快照，_CACHE_TTL_S 內共用上次結果（降低高頻 scrape 的 DB 壓力）。"""
    global _cache, _cache_at
    now = time.monotonic()
    if _cache is None or (now - _cache_at) >= _CACHE_TTL_S:
        _cache = await _snapshot()
        _cache_at = now
    return _cache


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus 抓取端點（業務量 gauge）。"""
    return Response(
        generate_latest(_registry(await _cached_snapshot())),
        media_type=CONTENT_TYPE_LATEST,
    )
