"""
workers/crawlers/reddit.py — 非同步 Reddit 爬蟲（raw 擷取）。

職責很窄（ADR-009）：fetch → 輕量關鍵字標記 → 輸出正規化 dict。
**不做** 品質過濾、不丟棄 [deleted]、不判斷關鍵字是否在正文 —— 那些是 Week 3 DQC 的事。

設計成「純輸出 dict、不碰 DB」，所以可單元測試（match_models / normalize_submission
都是純函式），DB 寫入由 api.services.posts.upsert_posts 處理。
"""
from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone
from typing import Any

import asyncpraw
from asyncprawcore.exceptions import (
    AsyncPrawcoreException,
    RequestException,
    ServerError,
    TooManyRequests,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# 主力 + 選配 subreddit（PROJECT_PLAN §6）。
DEFAULT_SUBREDDITS: tuple[str, ...] = (
    "LocalLLaMA",
    "ClaudeAI",
    "ChatGPT",
    "singularity",
    "MachineLearning",
    "OpenAI",
    "ArtificialIntelligence",
    "LocalLLM",
)

# 6 個監測模型的關鍵字別名（slug 要與 models 表、seed_models.py 一致）。
# 用 \b 詞界避免誤判（grok 不該命中 grokking）。
MODEL_KEYWORDS: dict[str, list[str]] = {
    "gpt": [r"gpt", r"chatgpt", r"openai"],
    "claude": [r"claude", r"anthropic"],
    "gemini": [r"gemini", r"bard"],
    "grok": [r"grok", r"xai"],
    "llama": [r"llama"],
    "deepseek": [r"deepseek"],
}
_PATTERNS: dict[str, re.Pattern[str]] = {
    slug: re.compile(r"\b(?:%s)\b" % "|".join(aliases), re.IGNORECASE)
    for slug, aliases in MODEL_KEYWORDS.items()
}

# 只重試「暫時性」例外；Forbidden / NotFound（私密、封鎖、不存在的 subreddit）不重試。
retry_reddit = retry(
    retry=retry_if_exception_type((RequestException, ServerError, TooManyRequests)),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    stop=stop_after_attempt(4),
    reraise=True,
)


def match_models(text: str) -> list[str]:
    """回傳文字中命中的模型 slug list（可能多個，可能空）。純函式，可測。"""
    return [slug for slug, pat in _PATTERNS.items() if pat.search(text)]


def normalize_submission(sub: Any) -> dict:
    """把 asyncpraw Submission 轉成可 UPSERT 的 dict。純函式（給定一個物件），可測。"""
    blob = f"{sub.title or ''}\n{sub.selftext or ''}"
    return {
        "source": "reddit",
        "external_id": sub.id,
        "title": sub.title,
        "content": sub.selftext or "",
        "author": sub.author.name if sub.author else None,  # 帳號被刪 = None
        "subreddit": sub.subreddit.display_name,
        "url": sub.url,
        "permalink": f"https://www.reddit.com{sub.permalink}",
        "flair": sub.link_flair_text,
        "over_18": bool(sub.over_18),
        "score": sub.score,
        "num_comments": sub.num_comments,
        "posted_at": datetime.fromtimestamp(sub.created_utc, tz=timezone.utc),
        "models": match_models(blob),  # 空 list → 之後 DQC 會 flag NO_KEYWORD
        "quality_score": None,  # DQC（Week 3）才填
    }


@retry_reddit
async def _fetch_subreddit(reddit: asyncpraw.Reddit, name: str, limit: int) -> list[dict]:
    """抓單一 subreddit 的最新貼文（含重試）。"""
    subreddit = await reddit.subreddit(name)
    out: list[dict] = []
    async for submission in subreddit.new(limit=limit):
        try:
            out.append(normalize_submission(submission))
        except Exception:  # noqa: BLE001 — 單篇正規化失敗不該丟掉整個 subreddit 的結果
            logger.exception(
                "正規化貼文失敗，跳過單篇：r/%s id=%s",
                name,
                getattr(submission, "id", "?"),
            )
    return out


async def crawl_reddit(
    client_id: str,
    client_secret: str,
    user_agent: str,
    subreddits: Iterable[str] = DEFAULT_SUBREDDITS,
    limit: int = 100,
    keyword_only: bool = True,
) -> AsyncIterator[dict]:
    """
    爬取多個 subreddit，yield 正規化貼文 dict。

    - 共用單一 Reddit instance、subreddit 之間「循序」抓（共用 rate-limit token bucket，
      不要寬鬆 fan-out 以免觸發 429）。
    - 單一 subreddit 失敗（私密 / 封鎖）只記 log 並跳過，不中斷整批。
    - keyword_only=True 時，過濾掉沒命中任何模型關鍵字的貼文。

    credential 由呼叫端注入（test 腳本 / Airflow DAG），爬蟲本身不依賴 settings。
    """
    async with asyncpraw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    ) as reddit:
        for name in subreddits:
            try:
                posts = await _fetch_subreddit(reddit, name, limit)
            except AsyncPrawcoreException:
                # 私密 / 封鎖 / 不存在的 subreddit、重試後仍失敗的網路錯誤 → 跳過該 sub。
                # 只攔 prawcore 例外，讓程式 bug（KeyError 等）照常拋出、被看見。
                logger.exception("抓取 subreddit 失敗，跳過：r/%s", name)
                continue

            kept = 0
            for post in posts:
                if keyword_only and not post["models"]:
                    continue
                kept += 1
                yield post
            logger.info("r/%s：抓 %d 篇，保留 %d 篇", name, len(posts), kept)
