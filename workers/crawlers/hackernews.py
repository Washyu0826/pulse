"""
workers/crawlers/hackernews.py — 非同步 HackerNews 爬蟲（raw 擷取）。

走 Algolia HN Search API（https://hn.algolia.com/api）：
- 完全免費、**不需要任何 API key**。
- 用 /search_by_date 端點：依「時間」排序（最新在前）。每個關鍵字只抓第 0 頁
  （最新 hits_per_page 筆），**不做分頁** —— 適合 15 分鐘週期的增量爬取
  （下一輪自然接上更新貼文）；要歷史回填才需加 page 參數分頁。
- term 之間無節流（量小、11 個關鍵字、Algolia 免費端點足夠）；429 / 5xx 由重試退避處理。

輸出 dict 與 Reddit 爬蟲同形狀（source="hackernews"），共用 api.services.posts.upsert_posts。
職責同樣很窄（ADR-009）：只抓 raw、輕量關鍵字標記，品質過濾留給 Week 3 DQC。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from typing import Any

import httpx

from crawlers._http import http_retry
from crawlers.keywords import SEARCH_TERMS, match_models

__all__ = ["crawl_hackernews", "normalize_hn_hit"]

logger = logging.getLogger(__name__)

HN_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"
_USER_AGENT = "pulse/0.1 (AI discussion monitor)"

retry_hn = http_retry()  # 逾時 / 連線 / 5xx / 429 才重試（共用設定）


def normalize_hn_hit(hit: dict[str, Any]) -> dict:
    """把一筆 Algolia hit 轉成可 UPSERT 的 dict。純函式，可測。"""
    # title 可能 None（已刪 / 特殊項）→ 保留 None，交給 upsert_posts 的必填防護略過，
    # 與 Reddit 爬蟲行為一致（不要硬塞 "" 變成無標題垃圾列）。
    title = hit.get("title")
    text = hit.get("story_text") or ""  # Ask HN / 文字貼文才有；連結貼文通常 None
    raw_id = hit.get("objectID")  # 缺 id → 保留 None（勿用 str() 變 "None" 騙過必填防護）
    object_id = str(raw_id) if raw_id is not None else None
    created_i = hit.get("created_at_i")
    return {
        "source": "hackernews",
        "external_id": object_id,
        "title": title,
        "content": text,
        "author": hit.get("author"),
        "subreddit": None,  # HN 沒有 subreddit
        "url": hit.get("url"),
        "permalink": f"https://news.ycombinator.com/item?id={object_id}",
        "flair": None,
        "over_18": False,
        "score": hit.get("points") or 0,
        "num_comments": hit.get("num_comments") or 0,
        # created_at_i 缺失 → None，upsert_posts 會略過（NOT NULL 防護）
        "posted_at": datetime.fromtimestamp(created_i, tz=UTC) if created_i else None,
        "models": match_models(f"{title or ''}\n{text}"),
        "quality_score": None,
    }


@retry_hn
async def _search_term(client: httpx.AsyncClient, term: str, hits_per_page: int) -> list[dict]:
    """搜尋單一關鍵字的最新 story（含重試）。"""
    resp = await client.get(
        HN_SEARCH_URL,
        params={"query": term, "tags": "story", "hitsPerPage": hits_per_page},
    )
    resp.raise_for_status()
    return resp.json().get("hits", [])


async def crawl_hackernews(
    search_terms: Iterable[str] = SEARCH_TERMS,
    hits_per_page: int = 50,
    keyword_only: bool = True,
) -> AsyncIterator[dict]:
    """
    依關鍵字搜尋 HN story，yield 正規化貼文 dict（跨關鍵字以 objectID 去重）。

    - 不需 credential。
    - 單一關鍵字查詢失敗只記 log、跳過，不中斷整批。
    - keyword_only=True 時過濾掉沒命中任何模型的 hit（理論上搜尋結果都會命中該詞，
      但 Algolia 為模糊比對，保留此關卡以防誤抓）。
    """
    seen: set[str] = set()
    async with httpx.AsyncClient(timeout=15.0, headers={"User-Agent": _USER_AGENT}) as client:
        for term in search_terms:
            try:
                hits = await _search_term(client, term, hits_per_page)
            except httpx.HTTPError:
                logger.exception("HN 查詢失敗，跳過 term=%s", term)
                continue

            kept = 0
            for hit in hits:
                object_id = str(hit.get("objectID"))
                if object_id in seen:
                    continue
                seen.add(object_id)
                try:
                    row = normalize_hn_hit(hit)
                except Exception:  # noqa: BLE001 — 單筆失敗不該丟掉整個關鍵字的結果
                    logger.exception("HN 正規化失敗，跳過 id=%s", object_id)
                    continue
                if keyword_only and not row["models"]:
                    continue
                kept += 1
                yield row
            logger.info("HN term=%s：抓 %d 筆，保留 %d 筆", term, len(hits), kept)
