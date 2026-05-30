"""
workers/crawlers/twitter.py — X/Twitter 爬蟲（best-effort 選配 plugin，用 twscrape + 帳號 cookie）。

⚠️ 重要限制（誠實說明）：
- 2026 年 X **無免費官方 API**（官方收費、Nitter 多半失效、search 需登入）→ 只能用非官方 client。
- 用 twscrape（2026 最活躍維護）以**帳號 cookie**（auth_token + ct0）讀公開推文。違反 X ToS，
  低量讀取風險小但非零 → 建議用**次要帳號**，定位為**選配補充來源**，非 24/7 主力。
- X 約每 2~4 週改版 → twscrape 需偶爾升級；selector/欄位以安裝版為準。
- 缺 cookie → 記 log、yield 空（不 crash），與 crawl_reddit 行為一致。

設計同其他爬蟲：純函式 normalize_tweet（可測）+ crawl_twitter 產生器（優雅降級）。
輸出 dict 與其他來源同形狀（source="twitter"），共用 api.services.posts.upsert_posts。
"""
from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from typing import Any

from crawlers.keywords import match_models

__all__ = ["crawl_twitter", "normalize_tweet"]

logger = logging.getLogger(__name__)

# 每個模型一個查詢；relevance/雜訊交給 keyword_only + 下游 DQC。
DEFAULT_QUERIES: tuple[str, ...] = (
    "claude",
    "chatgpt OR gpt",
    "gemini",
    "grok",
    "llama",
    "deepseek",
)

# twscrape 帳號池 SQLite 路徑：固定在 temp（不依賴 CWD，跨 DAG run 持久），避免每次冷啟動重登。
_POOL_PATH = os.path.join(tempfile.gettempdir(), "pulse_twscrape_accounts.db")


def normalize_tweet(raw: dict[str, Any]) -> dict:
    """把 twscrape 的 tweet dict（tw.dict()）正規化成可 UPSERT 的 dict。純函式，可測。"""
    text = (raw.get("rawContent") or "").strip()
    posted = raw.get("date")
    if posted is not None and not isinstance(posted, datetime):
        posted = None
    # id_str 在 twscrape >=0.12 必有；保留 id 後備是「未來欄位更名」的前向相容守衛。
    # 缺 id → None，upsert 必填防護會略過（勿用 str(None) 騙過）。
    rid = raw.get("id_str")
    if not rid and raw.get("id") is not None:
        rid = str(raw["id"])
    user = raw.get("user")
    handle = user.get("username") if isinstance(user, dict) else None
    url = raw.get("url")
    return {
        "source": "twitter",
        "external_id": rid,
        "title": text[:120] or "(tweet)",
        "content": text,
        "author": handle,
        "subreddit": None,
        "url": url,
        "permalink": url,
        "flair": None,
        "over_18": False,
        # 互動量代理：讚 + 轉推（轉推常為讚的數倍，納入更能反映熱度）。
        "score": (raw.get("likeCount") or 0) + (raw.get("retweetCount") or 0),
        "num_comments": raw.get("replyCount") or 0,
        "posted_at": posted,
        "models": match_models(text),
        "quality_score": None,
    }


async def _make_api(auth_token: str, ct0: str, username: str):
    """建 twscrape API 並掛上 cookie 帳號。失敗回 None（best-effort）。"""
    try:
        from twscrape import API
    except ImportError:
        logger.warning("未安裝 twscrape，跳過 Twitter 爬取（pip install twscrape）")
        return None

    api = API(_POOL_PATH)
    # 先刪舊帳號再重建：確保套用最新 cookie，並避免舊的 inactive 帳號卡住（review #3）。best-effort。
    try:
        await api.pool.delete_accounts(username)
    except Exception:  # noqa: BLE001
        pass
    try:
        # cookie 帳號：password/email 留空（cookie 即 session，不做密碼登入）。
        await api.pool.add_account(
            username, "", "", "", cookies=f"auth_token={auth_token}; ct0={ct0}"
        )
    except Exception:  # noqa: BLE001 — 網路/檔案系統等錯誤不該中斷（重複加入 twscrape 不丟例外）
        logger.debug("twscrape add_account 略過")
    # 部分版本需 login_all 才把 cookie 帳號標為 active（僅驗證、不做密碼登入）。best-effort。
    try:
        await api.pool.login_all()
    except Exception:  # noqa: BLE001 — 啟用失敗仍嘗試 search，失敗會在查詢層被接住
        logger.debug("twscrape login_all 略過")
    return api


async def crawl_twitter(
    queries: Iterable[str] = DEFAULT_QUERIES,
    *,
    auth_token: str | None = None,
    ct0: str | None = None,
    username: str | None = None,
    limit: int = 30,
    keyword_only: bool = True,
) -> AsyncIterator[dict]:
    """
    用 twscrape + cookie 搜尋各模型最新推文，yield 正規化 dict。

    缺 cookie（auth_token/ct0/username）→ 記 log、yield 空，不 crash（與 crawl_reddit 一致）。
    單一查詢失敗只記 log、跳過，不中斷整批。
    """
    if not (auth_token and ct0 and username):
        logger.warning("缺 X cookie（X_AUTH_TOKEN/X_CT0/X_USERNAME），跳過 Twitter 爬取")
        return

    api = await _make_api(auth_token, ct0, username)
    if api is None:
        return

    seen: set[str] = set()
    for query in queries:
        kept = 0
        try:
            async for tw in api.search(query, limit=limit, kv={"product": "Latest"}):
                raw = tw.dict()
                ext = raw.get("id_str")
                if not ext and raw.get("id") is not None:
                    ext = str(raw["id"])
                if not ext or ext in seen:
                    continue
                seen.add(ext)
                try:
                    row = normalize_tweet(raw)
                except Exception:  # noqa: BLE001 — 單筆解析失敗不該丟掉整批
                    logger.exception("Twitter 正規化失敗，跳過 id=%s", ext)
                    continue
                if keyword_only and not row["models"]:
                    continue
                kept += 1
                yield row
        except Exception:  # noqa: BLE001 — 單一查詢失敗（改版/限流）不該拖垮整批
            logger.exception("Twitter 查詢失敗，跳過 query=%s", query)
            continue
        logger.info("Twitter query=%s：保留 %d 則", query, kept)
