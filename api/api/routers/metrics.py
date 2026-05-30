"""
Prometheus /metrics —— 業務資料量 gauge（給 Grafana「資料量趨勢」用）。

設計：scrape 時即時查業務 DB，用 custom collector 產 gauge（無狀態、每次重算、不留殘存 series）。
趨勢由 Prometheus 定期抓 gauge 自然形成時間序列（pull 模式；長駐服務不該用 Pushgateway）。
查詢都是 count/group by，索引足夠便宜；資料量極大時可改 reltuples 估算或快取。
"""
from fastapi import APIRouter, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import text

from api.database import AsyncSessionLocal

router = APIRouter()


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
        # 品質分桶（對齊 DQC 門檻：>=60 高、>=30 中、<30 低、NULL 未檢核）
        quality = (
            await s.execute(
                text(
                    "SELECT CASE WHEN quality_score IS NULL THEN 'unchecked' "
                    "WHEN quality_score >= 60 THEN 'high' "
                    "WHEN quality_score >= 30 THEN 'mid' ELSE 'low' END AS bucket, "
                    "count(*) FROM posts GROUP BY bucket"
                )
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
                    "SELECT m.slug, count(*) FROM post_models pm "
                    "JOIN models m ON m.id = pm.model_id GROUP BY m.slug"
                )
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
        def collect(self):
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


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus 抓取端點（業務量 gauge）。"""
    return Response(generate_latest(_registry(await _snapshot())), media_type=CONTENT_TYPE_LATEST)
