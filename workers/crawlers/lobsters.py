"""
workers/crawlers/lobsters.py — 非同步 Lobsters 爬蟲（raw 擷取）。

高品質技術討論/分享。走公開 .json（**不需 key**）。
輸出與其他爬蟲同形狀（source="lobsters"），共用 api.services.posts.upsert_posts。

Lobsters 是小型志工社群站 → 低頻、循序、帶可聯絡的 User-Agent。
用 t/ai,ml.json 當抓取範圍，match_models 當保留關卡。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime

import httpx

from crawlers._http import http_retry
from crawlers.keywords import match_models

__all__ = ["crawl_lobsters", "normalize_lobsters_story"]

logger = logging.getLogger(__name__)

LOBSTERS_URL = "https://lobste.rs/t/ai,ml.json"
_USER_AGENT = "pulse/0.1 (AI discussion monitor; contact xianguanyu925@gmail.com)"

retry_lobsters = http_retry()


def normalize_lobsters_story(story: dict) -> dict:
    """把一筆 Lobsters story 轉成可 UPSERT 的 dict。純函式，可測。"""
    title = story.get("title")
    body = story.get("description_plain") or story.get("description") or ""
    su = story.get("submitter_user")
    # submitter_user 跨 API 版本可能是字串或物件，兩種都處理
    author = su.get("username") if isinstance(su, dict) else su
    created = story.get("created_at")
    posted = None
    if created:
        try:
            posted = datetime.fromisoformat(created).astimezone(UTC)  # 帶 offset → UTC
        except ValueError:
            posted = None
    url = story.get("url") or story.get("short_id_url")  # 純文字貼文 url 可能為空
    return {
        "source": "lobsters",
        "external_id": story.get("short_id"),
        "title": title,
        "content": body,
        "author": author,
        "subreddit": None,
        "url": url,
        "permalink": story.get("comments_url") or story.get("short_id_url"),
        "flair": None,
        "over_18": False,
        "score": story.get("score") or 0,
        "num_comments": story.get("comment_count") or 0,
        "posted_at": posted,
        "models": match_models(f"{title or ''}\n{body}"),
        "quality_score": None,
    }


@retry_lobsters
async def _fetch_page(client: httpx.AsyncClient, page: int) -> list[dict]:
    params = {"page": page} if page > 1 else None
    resp = await client.get(LOBSTERS_URL, params=params)
    resp.raise_for_status()
    return resp.json()


async def crawl_lobsters(
    pages: int = 1,
    keyword_only: bool = True,
) -> AsyncIterator[dict]:
    """抓 ai,ml tag 的 story，yield 正規化 dict（以 short_id 去重）。預設只抓第 1 頁（增量足夠）。"""
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": _USER_AGENT}) as client:
        for page in range(1, pages + 1):
            try:
                stories = await _fetch_page(client, page)
            except httpx.HTTPError:
                logger.exception("Lobsters 查詢失敗，跳過 page=%s", page)
                continue

            kept = 0
            for story in stories:
                ext = story.get("short_id")
                if ext in seen:
                    continue
                seen.add(ext)
                try:
                    row = normalize_lobsters_story(story)
                except Exception:  # noqa: BLE001
                    logger.exception("Lobsters 正規化失敗，跳過 short_id=%s", ext)
                    continue
                if keyword_only and not row["models"]:
                    continue
                kept += 1
                yield row
            logger.info("Lobsters page=%s：抓 %d 篇，保留 %d 篇", page, len(stories), kept)
