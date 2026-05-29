"""
workers/crawlers/devto.py — 非同步 Dev.to 爬蟲（raw 擷取）。

開發者分享 AI 使用心得 / 教學 / 評測。走 Forem 官方 API，**不需 key**。
輸出與其他爬蟲同形狀（source="devto"），共用 api.services.posts.upsert_posts。

用 /articles/latest（時間序）做增量；以 match_models 過濾，只留提到 6 個模型的文章
（'ai' tag 太廣，tag 當抓取範圍、match_models 當保留關卡）。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime

import httpx

from crawlers._http import http_retry
from crawlers.keywords import match_models

__all__ = ["crawl_devto", "normalize_devto_article"]

logger = logging.getLogger(__name__)

DEVTO_LATEST_URL = "https://dev.to/api/articles/latest"
_USER_AGENT = "pulse/0.1 (AI discussion monitor; contact xianguanyu925@gmail.com)"
DEFAULT_TAGS: tuple[str, ...] = ("ai", "llm", "chatgpt", "openai", "claude", "machinelearning")

retry_devto = http_retry()


def normalize_devto_article(article: dict) -> dict:
    """把一篇 Dev.to article（list 回應）轉成可 UPSERT 的 dict。純函式，可測。"""
    title = article.get("title")
    desc = article.get("description") or ""  # body 不在 list 回應內，用 description
    user = article.get("user") or {}
    pub = article.get("published_at")
    posted = None
    if pub:
        try:
            posted = datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(UTC)
        except ValueError:
            posted = None
    raw_id = article.get("id")  # 缺 id → 保留 None（勿用 str() 變成 "None" 騙過必填防護）
    return {
        "source": "devto",
        "external_id": str(raw_id) if raw_id is not None else None,
        "title": title,
        "content": desc,
        "author": user.get("username"),
        "subreddit": None,
        "url": article.get("url"),
        "permalink": article.get("url"),
        "flair": None,
        "over_18": False,
        "score": article.get("positive_reactions_count") or 0,
        "num_comments": article.get("comments_count") or 0,
        "posted_at": posted,
        "models": match_models(f"{title or ''}\n{desc}"),
        "quality_score": None,
    }


@retry_devto
async def _fetch_tag(client: httpx.AsyncClient, tag: str, per_page: int) -> list[dict]:
    resp = await client.get(DEVTO_LATEST_URL, params={"tag": tag, "per_page": per_page})
    resp.raise_for_status()
    return resp.json()


async def crawl_devto(
    tags: Iterable[str] = DEFAULT_TAGS,
    per_page: int = 50,
    keyword_only: bool = True,
) -> AsyncIterator[dict]:
    """逐 tag 抓最新文章，yield 正規化 dict（跨 tag 以 id 去重，單 tag 失敗只 log）。"""
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": _USER_AGENT}) as client:
        for tag in tags:
            try:
                articles = await _fetch_tag(client, tag, per_page)
            except httpx.HTTPError:
                logger.exception("Dev.to 查詢失敗，跳過 tag=%s", tag)
                continue

            kept = 0
            for article in articles:
                ext = str(article.get("id"))
                if ext in seen:
                    continue
                seen.add(ext)
                try:
                    row = normalize_devto_article(article)
                except Exception:  # noqa: BLE001
                    logger.exception("Dev.to 正規化失敗，跳過 id=%s", ext)
                    continue
                if keyword_only and not row["models"]:
                    continue
                kept += 1
                yield row
            logger.info("Dev.to tag=%s：抓 %d 篇，保留 %d 篇", tag, len(articles), kept)
