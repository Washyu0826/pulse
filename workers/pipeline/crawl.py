"""
pipeline.crawl —— 「抓貼文/發布事件 → UPSERT 進 DB」的可重用編排。

每個函式：
1. 把對應爬蟲（async generator）耗盡成 list[dict]（在同一個 event loop 內，避免跨 loop 問題）；
2. 開一個 AsyncSession，呼叫對應的 UPSERT 服務（服務內部自行 commit）；
3. 回傳統計 dict（received / skipped / upserted / associations）。

冪等：UPSERT 以自然鍵 on-conflict，重跑安全 → 可放心搭配 Airflow retries。
"""
from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator

# TLS 攔截環境：改用 OS 信任庫，避免 httpx/asyncpraw 踩 CERTIFICATE_VERIFY_FAILED。
# 放在 pipeline 模組層 → 不論是手動腳本或 Airflow 的 ExternalPython venv 子行程 import 進來，
# 都會在任何 HTTPS 之前注入（Airflow 主環境的 plugin 注入到不了 venv 子行程，故這裡必須再做一次）。
# best-effort：未裝 truststore 就略過（無攔截網路用 OS 信任庫也正確）。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

from api.database import AsyncSessionLocal
from api.services.posts import upsert_posts
from api.services.releases import upsert_release_events

logger = logging.getLogger(__name__)


async def _drain(agen: AsyncIterator[dict]) -> list[dict]:
    """把 async generator 完整耗盡成 list（務必在同一 loop 內完成）。"""
    return [row async for row in agen]


async def _crawl_posts_to_db(agen: AsyncIterator[dict], *, label: str) -> dict[str, int]:
    """通用：耗盡貼文爬蟲 → UPSERT posts。回傳統計。"""
    rows = await _drain(agen)
    logger.info("[%s] 抓到 %d 篇含模型關鍵字的貼文", label, len(rows))
    async with AsyncSessionLocal() as session:
        stats = await upsert_posts(session, rows)
    logger.info("[%s] UPSERT 統計：%s", label, stats)
    return stats


async def crawl_hackernews_to_db(hits_per_page: int = 50, keyword_only: bool = True) -> dict[str, int]:
    """HackerNews（Algolia，免 key）→ posts。"""
    from crawlers.hackernews import crawl_hackernews

    return await _crawl_posts_to_db(
        crawl_hackernews(hits_per_page=hits_per_page, keyword_only=keyword_only),
        label="hackernews",
    )


async def crawl_devto_to_db(per_page: int = 50, keyword_only: bool = True) -> dict[str, int]:
    """Dev.to（免 key）→ posts。"""
    from crawlers.devto import crawl_devto

    return await _crawl_posts_to_db(
        crawl_devto(per_page=per_page, keyword_only=keyword_only),
        label="devto",
    )


async def crawl_lobsters_to_db(keyword_only: bool = True) -> dict[str, int]:
    """Lobsters（免 key）→ posts。"""
    from crawlers.lobsters import crawl_lobsters

    return await _crawl_posts_to_db(
        crawl_lobsters(keyword_only=keyword_only),
        label="lobsters",
    )


async def crawl_reddit_to_db(
    subreddits: list[str] | None = None,
    limit: int = 50,
    keyword_only: bool = True,
) -> dict[str, int]:
    """
    Reddit（需 credential）→ posts。

    缺 credential 時不視為失敗：記 log 並回傳零統計（DAG 端據此判斷是否 skip）。
    """
    from api.config import settings
    from crawlers.reddit import DEFAULT_SUBREDDITS, crawl_reddit

    if not settings.reddit_client_id or not settings.reddit_client_secret:
        logger.warning("缺 Reddit credential（REDDIT_CLIENT_ID/SECRET），跳過 Reddit 爬取")
        return {"received": 0, "skipped": 0, "upserted": 0, "associations": 0, "credential_missing": 1}

    return await _crawl_posts_to_db(
        crawl_reddit(
            client_id=settings.reddit_client_id,
            client_secret=settings.reddit_client_secret,
            user_agent=settings.reddit_user_agent,
            subreddits=subreddits or list(DEFAULT_SUBREDDITS),
            limit=limit,
            keyword_only=keyword_only,
        ),
        label="reddit",
    )


async def fetch_releases_to_db(source: str = "all") -> dict[str, int]:
    """
    HF Hub + GitHub Releases（免 key；GitHub 可選 GITHUB_TOKEN 提額度）→ release_events。

    source: "all" | "huggingface" | "github"。
    """
    from crawlers.github import crawl_github
    from crawlers.huggingface import crawl_huggingface

    rows: list[dict] = []
    if source in ("all", "huggingface"):
        rows += await _drain(crawl_huggingface())
    if source in ("all", "github"):
        rows += await _drain(crawl_github(token=os.environ.get("GITHUB_TOKEN")))

    logger.info("[releases] 抓到 %d 筆發布事件（source=%s）", len(rows), source)
    async with AsyncSessionLocal() as session:
        stats = await upsert_release_events(session, rows)
    logger.info("[releases] UPSERT 統計：%s", stats)
    return stats
