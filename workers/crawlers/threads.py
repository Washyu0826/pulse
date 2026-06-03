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
from datetime import UTC, datetime
from typing import Any

from crawlers.keywords import match_models

__all__ = ["crawl_threads", "normalize_thread_post"]

logger = logging.getLogger(__name__)

# 預設用模型關鍵字當 search 查詢；Threads 的 tag 搜尋頁。
# 註：Threads 2025 把主網域 threads.net → threads.com（cookie domain 也跟著變）。
_DOMAIN = "threads.com"
# 擴大查詢以提高每日新貼產量：6 模型 + 別名 + 熱門相關詞（tag 搜尋）。
# keyword_only 仍會把「沒提到 6 模型」的貼擋掉，故這些主要是「更多入口」找到提及模型的貼。
DEFAULT_QUERIES: tuple[str, ...] = (
    "claude", "claude code", "chatgpt", "gpt", "openai", "anthropic",
    "gemini", "grok", "llama", "deepseek",
    "copilot", "cursor", "perplexity", "ai agent", "提示詞", "ai工具",
)
_SEARCH_URL = f"https://www.{_DOMAIN}/search?q={{q}}&serp_type=tags"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def normalize_thread_post(raw: dict[str, Any]) -> dict:
    """把抓到的 Threads 貼文原始 dict 正規化成可 UPSERT 的 dict。純函式，可測。"""
    text = (raw.get("text") or "").strip()
    posted = raw.get("posted_at")
    if not isinstance(posted, datetime):
        # 抽不到 <time datetime> → fallback 用現在時間（抓取時間），避免必填 posted_at 缺漏被整批丟掉。
        # 多數貼文都抽得到絕對時間；此 fallback 只兜底少數，不會大量污染時間序。
        posted = datetime.now(UTC)
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
    """
    建 Chrome/Chromium WebDriver。失敗給清楚訊息。

    本機：留空環境變數 → Selenium Manager 自動抓 driver（需裝 Chrome）。
    容器（Airflow）：apt 裝的 chromium 無法上網下載 driver → 用環境變數指定：
      CHROME_BIN=/usr/bin/chromium、CHROMEDRIVER_PATH=/usr/bin/chromedriver。
    """
    import os

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
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
    # 容器內用 apt 的 chromium：指定 binary 路徑（否則 Selenium 找不到瀏覽器）。
    if chrome_bin := os.environ.get("CHROME_BIN"):
        opts.binary_location = chrome_bin
    # 有指定 driver 路徑就用它（容器內無網路下載 driver）；否則交給 Selenium Manager。
    service = Service(executable_path=p) if (p := os.environ.get("CHROMEDRIVER_PATH")) else None
    try:
        return webdriver.Chrome(options=opts, service=service)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(
            f"Chrome WebDriver 啟動失敗（檢查 Chrome 安裝 / driver / 網路）：{e}"
        ) from e


def _inject_session(driver, sessionid: str) -> None:
    """注入 Threads 登入 cookie（sessionid，與 Instagram 共用）以越過登入牆。

    Selenium 規則：add_cookie 前必須先在「同網域」頁面上 → 先載入 threads.net 首頁再注入。
    best-effort：失敗只記 log，不中斷（退化成未登入模式）。
    """
    try:
        driver.get(f"https://www.{_DOMAIN}/")
        driver.add_cookie(
            {"name": "sessionid", "value": sessionid, "domain": f".{_DOMAIN}", "path": "/"}
        )
        driver.refresh()  # 重載讓 cookie 生效（套用登入狀態）
        logger.info("已注入 Threads sessionid cookie（登入模式）")
    except Exception:  # noqa: BLE001 — 注入失敗就退化成未登入，不該 crash
        logger.exception("注入 Threads cookie 失敗，退化為未登入模式")


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
            # 發文時間：Threads 每則貼文有 <time datetime="ISO">（相對顯示「1小時」，但屬性是絕對時間）。
            # 抽不到就留 None，由 normalize 決定 fallback（避免整批因缺 posted_at 被丟掉）。
            posted_at = None
            for t in el.find_elements(By.CSS_SELECTOR, "time[datetime]"):
                iso = t.get_attribute("datetime")
                if iso:
                    try:
                        posted_at = datetime.fromisoformat(iso.replace("Z", "+00:00"))
                    except ValueError:
                        posted_at = None
                    break
            # 長度門檻：濾掉只含作者名/按鈕的小卡片（best-effort 降噪）
            if pid and len(text.strip()) > 20:
                out.append({
                    "id": f"threads_{pid}", "text": text, "author": author,
                    "url": link, "posted_at": posted_at,
                })
        except Exception:  # noqa: BLE001 — 單一容器解析失敗不該丟掉整批
            logger.debug("解析 Threads 容器失敗，跳過一則（query=%s）", query)
    return out


async def crawl_threads(
    queries: Iterable[str] = DEFAULT_QUERIES,
    max_posts: int = 30,
    headless: bool = True,
    scroll_times: int = 3,
    keyword_only: bool = True,
    sessionid: str | None = None,
) -> AsyncIterator[dict]:
    """
    用 Selenium 載入 Threads 搜尋頁、捲動、抽取貼文，yield 正規化 dict。

    sessionid：Threads 登入 cookie（與 Instagram 共用）。有給 → 注入後可越過登入牆、
    抓到較完整資料；未給 → 多半碰到登入牆、抓不到或很少（會記 log、不 crash）。
    """
    import asyncio

    driver = await asyncio.to_thread(_build_driver, headless)
    seen: set[str] = set()
    try:
        if sessionid:
            await asyncio.to_thread(_inject_session, driver, sessionid)
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
