"""
workers/crawlers/threads.py — Selenium 爬 Threads（Meta）的 best-effort plugin。

⚠️ 重要限制（誠實說明）：
- Threads 有**登入牆 + 反爬**：未登入只看得到部分公開貼文；search/tag 常需登入。
- DOM selector 會隨 Meta 改版而失效（本檔用保守 selector + 大量 try/except，易微調）。
- 跟 Airflow 24/7 不合（瀏覽器重、慢、易壞）→ 定位為**選配 plugin**，非主力來源。
- 主力來源請用免 key 的 API（HN/Dev.to/HF/GitHub）。

設計同其他爬蟲：純函式 normalize_thread_post（可測）+ crawl_threads 產生器（優雅降級）。
輸出 dict 與其他來源同形狀（source="threads"），共用 api.services.posts.upsert_posts。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from datetime import datetime
from typing import Any

from crawlers.keywords import match_models

__all__ = ["crawl_threads", "normalize_thread_post"]

logger = logging.getLogger(__name__)

# 預設用模型關鍵字當 search 查詢；threads.net 的 tag 搜尋頁。
DEFAULT_QUERIES: tuple[str, ...] = ("claude", "gpt", "gemini", "llama", "deepseek")
_SEARCH_URL = "https://www.threads.net/search?q={q}&serp_type=tags"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def normalize_thread_post(raw: dict[str, Any]) -> dict:
    """把抓到的 Threads 貼文原始 dict 正規化成可 UPSERT 的 dict。純函式，可測。"""
    text = (raw.get("text") or "").strip()
    posted = raw.get("posted_at")
    if posted is not None and not isinstance(posted, datetime):
        posted = None
    return {
        "source": "threads",
        "external_id": raw.get("id"),  # 缺 id → None，upsert 必填防護會略過
        "title": text[:120] or "(Threads 貼文)",
        "content": text,
        "author": raw.get("author"),
        "subreddit": None,
        "url": raw.get("url"),
        "permalink": raw.get("url"),
        "flair": None,
        "over_18": False,
        "score": raw.get("likes") or 0,
        "num_comments": raw.get("replies") or 0,
        "posted_at": posted,
        "models": match_models(text),
        "quality_score": None,
    }


def _build_driver(headless: bool):
    """建 Chrome WebDriver（Selenium Manager 自動下載 driver）。失敗給清楚訊息。"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError as e:
        raise ImportError("需要 selenium：pip install selenium") from e

    opts = Options()
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument(f"--user-agent={_USER_AGENT}")
    opts.add_argument("--window-size=1280,2000")
    try:
        return webdriver.Chrome(options=opts)  # Selenium Manager 處理 driver
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"Chrome WebDriver 啟動失敗（檢查 Chrome 安裝 / driver / 網路）：{e}"
        ) from e


def _extract_posts(driver, query: str, max_posts: int) -> list[dict]:
    """從目前頁面抽取貼文（best-effort；selector 易隨 Meta 改版調整）。"""
    from selenium.webdriver.common.by import By

    out: list[dict] = []
    # Threads 貼文容器（保守選 data-pressable-container；改版時調這裡）。
    containers = driver.find_elements(By.CSS_SELECTOR, "div[data-pressable-container='true']")
    for el in containers[:max_posts]:
        try:
            text = el.text or ""
            # 取容器內第一個貼文連結當 permalink + id
            link = None
            pid = None
            for a in el.find_elements(By.CSS_SELECTOR, "a[href*='/post/']"):
                href = a.get_attribute("href")
                if href and "/post/" in href:
                    link = href
                    pid = href.rstrip("/").split("/post/")[-1].split("?")[0]
                    break
            author = None
            for a in el.find_elements(By.CSS_SELECTOR, "a[href^='/@']"):
                author = (a.get_attribute("href") or "").rstrip("/").split("/@")[-1]
                if author:
                    break
            # 長度門檻：濾掉只含作者名/按鈕的小卡片（best-effort 降噪）
            if pid and len(text.strip()) > 20:
                out.append({"id": f"threads_{pid}", "text": text, "author": author, "url": link})
        except Exception:  # noqa: BLE001 — 單一容器解析失敗不該丟掉整批
            logger.debug("解析 Threads 容器失敗，跳過一則（query=%s）", query)
    return out


async def crawl_threads(
    queries: Iterable[str] = DEFAULT_QUERIES,
    max_posts: int = 30,
    headless: bool = True,
    scroll_times: int = 3,
    keyword_only: bool = True,
) -> AsyncIterator[dict]:
    """
    用 Selenium 載入 Threads 搜尋頁、捲動、抽取貼文，yield 正規化 dict。

    ⚠️ 未登入時多半碰到登入牆 → 抓不到或很少（會記 log、不 crash）。
    需要較完整資料時：在正常網路、或注入登入 cookie（之後可加 cookie 參數）。
    """
    import asyncio

    driver = await asyncio.to_thread(_build_driver, headless)
    seen: set[str] = set()
    try:
        for query in queries:
            url = _SEARCH_URL.format(q=query)
            try:
                await asyncio.to_thread(driver.get, url)
                # 捲動觸發 lazy load
                for _ in range(scroll_times):
                    await asyncio.to_thread(
                        driver.execute_script, "window.scrollTo(0, document.body.scrollHeight);"
                    )
                    await asyncio.sleep(1.5)
                raw_posts = await asyncio.to_thread(_extract_posts, driver, query, max_posts)
            except Exception:  # noqa: BLE001 — 單一 query 失敗不該拖垮整批
                logger.exception("Threads 查詢失敗，跳過 query=%s", query)
                continue

            kept = 0
            for raw in raw_posts:
                ext = raw.get("id")
                if not ext or ext in seen:
                    continue
                seen.add(ext)
                try:
                    row = normalize_thread_post(raw)
                except Exception:  # noqa: BLE001
                    logger.exception("Threads 正規化失敗，跳過 id=%s", ext)
                    continue
                if keyword_only and not row["models"]:
                    continue
                kept += 1
                yield row
            logger.info("Threads query=%s：抽 %d 則，保留 %d 則", query, len(raw_posts), kept)
    finally:
        await asyncio.to_thread(driver.quit)
