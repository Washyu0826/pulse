"""
workers/crawlers/threads.py — Selenium 爬 Threads（Meta）。**Pulse 的主力來源**（繁中台灣 AI 討論）。

為何主力：台灣是 Threads 全球第 1 大市場，台灣 AI 在地討論（工具 / 提示詞 / 變現 / AI繪圖 /
風險）幾乎都在這 —— 這正是 Pulse 差異化於英文競品的「在地社群訊號」。

門檻設計（2026-06 改）：
- 不再要求「點名 6 模型」（那會丟掉大半不點名模型的台灣 AI 貼）。改為**廣義 AI 相關門檻**
  （`is_ai_related`：模型 OR 提示/工具/生成/變現 等），仍保留 match_models 供模型口碑用。
- 加**繁體過濾**（`looks_simplified`）擋掉簡體（中國）內容，純化台灣訊號。

⚠️ 誠實限制：
- 登入牆 + 反爬：search/tag 需登入（注入 sessionid cookie）。
- DOM selector 會隨 Meta 改版失效（保守 selector + 大量 try/except，易微調）。
- 登入抓取（sessionid）有 ToS 風險（登入＝接受條款）；合規長期路線是申請官方
  Threads Keyword Search API（`threads_keyword_search` scope，需 App Review）。本檔為過渡實作。

設計同其他爬蟲：純函式 normalize_thread_post（可測）+ crawl_threads 產生器（優雅降級）。
輸出 dict 與其他來源同形狀（source="threads"），共用 api.services.posts.upsert_posts。
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Iterable
from datetime import UTC, datetime
from typing import Any

from crawlers.keywords import is_ai_related, looks_simplified, match_models
from crawlers.threads_clean import clean_thread_text

__all__ = ["crawl_threads", "normalize_thread_post"]

logger = logging.getLogger(__name__)

# 註：Threads 2025 把主網域 threads.net → threads.com（cookie domain 也跟著變）。
_DOMAIN = "threads.com"
# 查詢詞（tag 搜尋入口）：模型輪替 + 廣義中文 AI + 台灣在地（變現/教學）+ 風險倫理（價值主題）。
# 門檻改廣義 AI 後，這些查詢能帶回大量不點名模型、但確實在談 AI 的台灣貼文。
DEFAULT_QUERIES: tuple[str, ...] = (
    # 模型 / 工具（輪替入口）
    "claude", "claude code", "chatgpt", "gpt", "openai", "gemini", "grok", "llama",
    "deepseek", "copilot", "cursor", "perplexity", "midjourney", "notebooklm",
    # 廣義中文 AI（主力）
    "AI工具", "AI繪圖", "AI生圖", "提示詞", "AI教學", "生成式AI", "ai agent",
    # 使用方法 / 變現（台灣在地高量）
    "AI變現", "AI副業", "AI接案", "ChatGPT教學", "AI自動化",
    # 風險 / 倫理（價值主題）
    "AI詐騙", "AI造假", "deepfake", "AI隱私", "AI取代",
    # 新模型 / 熱門工具（2026 在地高頻）
    "sora", "gpts", "gpt-5", "gemini3", "kling", "可靈", "comfyui", "stable diffusion",
    "runway", "suno", "heygen", "notion ai", "github copilot", "claude opus",
    # AI 繪圖 / 內容細分（台灣社群最熱）
    "AI繪師", "AI語音", "AI影片", "文生圖", "AI寫作", "AI助理", "提示工程", "AI模型",
    # 變現 / 學習（台灣在地）
    "AI賺錢", "AI斜槓", "ChatGPT賺錢", "AI工作流", "AI課程",
    # 著作權 / 監管
    "AI著作權", "AI版權", "AI監管",
    # 模型版本（細分入口，觸及不同貼）
    "gpt-4o", "gpt4o", "o1", "o3", "claude 3.5", "claude sonnet", "claude haiku",
    "gemini pro", "gemini flash", "llama 3", "mistral", "qwen", "deepseek r1",
    "flux", "dall-e", "dalle", "ideogram", "leonardo ai", "pika", "luma", "udio",
    "elevenlabs", "whisper", "nano banana", "wan", "即夢",
    # AI 工具 / 應用（繁中細分）
    "AI工具推薦", "AI應用", "AI趨勢", "ChatGPT應用", "AI寫作工具", "AI簡報",
    "AI影片生成", "AI配音", "AI換臉", "AI去背", "AI修圖", "AI頭像", "AI模特",
    "AI生成影片", "AI生成圖片", "AI繪圖工具", "AI聊天機器人", "AI客服",
    # 變現 / 自媒體（台灣在地高量）
    "AI被動收入", "AI賺錢方法", "AI電商", "AI行銷", "AI文案", "AI自媒體",
    "AI部落格", "ChatGPT賺錢方法", "AI開店", "AI經營",
    # Coding / agent 工具
    "cursor教學", "windsurf", "bolt.new", "v0", "replit agent", "devin",
    "AI寫程式", "vibe coding", "claude code教學", "AI coding",
    # 一般詞 / 新聞 / 風險
    "人工智慧", "機器學習", "大語言模型", "生成式AI應用", "AI新聞",
    "AI失業", "AI法規", "AI假新聞", "AI個資", "AI偏見", "AI幻覺",
)
_SEARCH_URL = f"https://www.{_DOMAIN}/search?q={{q}}&serp_type=tags"
# 貼文容器 selector（依序嘗試；Meta 改版常只動其一）。primary 失效時退到下一個，
# 避免「DOM 一變就靜默回 0 筆」。改版時優先在此清單調整/補新 selector。
_CONTAINER_SELECTORS: tuple[str, ...] = (
    "div[data-pressable-container='true']",  # 2026-06 主用
    "div[role='article']",                   # 語意化 fallback（貼文常標 article role）
    "article",                               # 最寬鬆 fallback
)
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def normalize_thread_post(raw: dict[str, Any]) -> dict:
    """把抓到的 Threads 貼文原始 dict 正規化成可 UPSERT 的 dict。純函式，可測。"""
    # 先剝掉容器 .text 夾帶的 UI chrome（作者名 / 日期 / 相對時間 / 互動計數 / 分頁 / 翻譯），
    # 再衍生 title/content/models —— 否則 chrome 會污染內文、熱詞、主題/情緒分類（backlog #1）。
    text = clean_thread_text((raw.get("text") or "").strip())
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
    # Threads 貼文容器：依序試多個 selector，第一個抓到非空就用（抗 Meta 改版）。
    containers: list = []
    used_selector = None
    for sel in _CONTAINER_SELECTORS:
        containers = driver.find_elements(By.CSS_SELECTOR, sel)
        if containers:
            used_selector = sel
            break
    if not containers:
        # 全部 selector 皆 0 → 多半是 Meta 改了 DOM（或登入牆/空結果）。明確告警，不要靜默。
        logger.warning(
            "Threads：所有容器 selector 皆抓到 0 個元素（query=%s）—— "
            "可能 Meta 改版需更新 _CONTAINER_SELECTORS，或碰到登入牆/無結果。",
            query,
        )
        return out
    if used_selector != _CONTAINER_SELECTORS[0]:
        # 退到 fallback selector 也記一筆，提示 primary selector 可能已失效。
        logger.warning(
            "Threads：primary selector 失效，改用 fallback '%s'（query=%s）—— 建議盡快更新。",
            used_selector, query,
        )
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
    traditional_only: bool = True,
    sessionid: str | None = None,
) -> AsyncIterator[dict]:
    """
    用 Selenium 載入 Threads 搜尋頁、捲動、抽取貼文，yield 正規化 dict。

    keyword_only：True 時用**廣義 AI 相關門檻**（模型 OR 提示/工具/生成/變現…）過濾，
      只擋掉與 AI 無關的貼（不再要求點名特定模型）。
    traditional_only：True 時用 looks_simplified 擋掉簡體（中國）內容，純化台灣繁中訊號。
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
                text = row["content"]
                # 繁體過濾：擋掉簡體（中國）內容，純化台灣訊號。
                if traditional_only and looks_simplified(text):
                    continue
                # 廣義 AI 門檻：模型 OR 廣義 AI 相關（不再要求點名模型）。
                if keyword_only and not (row["models"] or is_ai_related(text)):
                    continue
                kept += 1
                yield row
            if not raw_posts:
                # 0 筆抽取 → 斷流疑慮（DOM 變動 / 登入牆 / cookie 失效）。WARNING 讓它看得見，
                # 不被海量 INFO 淹沒；有 SLACK_WEBHOOK_URL 時順手送一則訊號（best-effort，不 crash）。
                logger.warning("Threads query=%s：抽到 0 筆 —— selector 失效或登入牆？", query)
                _notify_zero_result(query)
            else:
                logger.info("Threads query=%s：抽 %d 則，保留 %d 則", query, len(raw_posts), kept)
    finally:
        await asyncio.to_thread(driver.quit)


def _notify_zero_result(query: str) -> None:
    """0 筆結果時送一則 Slack 訊號（best-effort）。無 webhook / 送失敗都只記 log，不中斷爬取。"""
    import os

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook:
        return
    try:
        import httpx

        httpx.post(
            webhook,
            json={"text": f":warning: Threads 爬蟲 query=`{query}` 抽到 0 筆 —— "
                          "可能 selector 失效或 cookie 過期，請查 workers/crawlers/threads.py。"},
            timeout=5.0,
        )
    except Exception:  # noqa: BLE001 — 告警本身失敗不該影響爬取
        logger.debug("Threads 0 筆 Slack 告警送出失敗（query=%s）", query)
