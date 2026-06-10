"""
PTT 爬蟲（Selenium 真瀏覽器）—— 抓台灣繁中 AI 相關貼文寫進 DB。

為何 Selenium：本機 curl/httpx 在此沙箱被擋（http 000），真瀏覽器走系統網路可正常連 PTT，
也能過某些站的反爬。PTT 多數技術板無需登入；有年齡牆的板（如 Gossiping）注入 over18 cookie。

流程：逐板翻 index 頁 → 解析 r-ent 列 → 標題過 is_ai_related（繁中 AI 門檻）→ 進文章頁抓內文 +
精確時間 → 正規化成 posts dict（source=ptt）→ upsert_posts（冪等，重跑安全）。

用法（系統 Python，需 selenium + Chrome）：
    python scripts/crawl_ptt.py --max-pages 40 --headless
    python scripts/crawl_ptt.py --boards Soft_Job Tech_Job DataScience --max-pages 60 --headless
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "workers"))

from api.services.posts import upsert_posts  # noqa: E402
from crawlers.keywords import is_ai_related  # noqa: E402

_BASE = "https://www.ptt.cc"
# 較可能有 AI 討論的板（無年齡牆的技術/股票/科技板優先）
DEFAULT_BOARDS = ("Soft_Job", "Tech_Job", "DataScience", "Stock", "MobileComm", "PC_Shopping")
_ART_ID_RE = re.compile(r"/bbs/([^/]+)/(M\.\d+\.A\.[0-9A-F]+)\.html")
_TIME_RE = re.compile(r"※ 發信站|時間")


def _build_driver(headless: bool):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    o = Options()
    if headless:
        o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu")
    o.add_argument("--window-size=1280,2000")
    o.add_argument("--log-level=3")
    o.add_experimental_option("excludeSwitches", ["enable-logging"])
    d = webdriver.Chrome(options=o)
    d.set_page_load_timeout(40)
    # 過年齡牆：先設 over18 cookie（部分板需要）
    d.get(f"{_BASE}/ask/over18")
    d.add_cookie({"name": "over18", "value": "1", "domain": ".ptt.cc", "path": "/"})
    return d


def _parse_index(driver) -> tuple[list[dict], str | None]:
    """解析目前 index 頁的貼文列 + 回傳「上頁」連結（無則 None）。"""
    from selenium.webdriver.common.by import By

    out: list[dict] = []
    for ent in driver.find_elements(By.CSS_SELECTOR, "div.r-ent"):
        try:
            a = ent.find_element(By.CSS_SELECTOR, "div.title a")
        except Exception:  # noqa: BLE001 — 被刪文沒有連結
            continue
        href = a.get_attribute("href") or ""
        m = _ART_ID_RE.search(href)
        if not m:
            continue
        title = (a.text or "").strip()
        try:
            author = ent.find_element(By.CSS_SELECTOR, "div.meta div.author").text.strip()
        except Exception:  # noqa: BLE001
            author = ""
        try:
            nrec = ent.find_element(By.CSS_SELECTOR, "div.nrec").text.strip()
        except Exception:  # noqa: BLE001
            nrec = ""
        out.append(
            {"board": m.group(1), "aid": m.group(2), "url": href, "title": title,
             "author": author, "nrec": nrec}
        )
    prev = None
    for btn in driver.find_elements(By.CSS_SELECTOR, "div.btn-group-paging a.btn"):
        if "上頁" in (btn.text or ""):
            prev = btn.get_attribute("href")
            break
    return out, prev


def _score_from_nrec(nrec: str) -> int:
    if nrec == "爆":
        return 100
    if nrec.startswith("X"):
        return -10
    try:
        return int(nrec)
    except ValueError:
        return 0


def _fetch_article(driver, url: str) -> tuple[str, datetime | None]:
    """進文章頁抓內文 + 發文時間。失敗回 ('', None)。"""
    from selenium.webdriver.common.by import By

    if not _get_with_retry(driver, url, tries=3, wait=6.0):
        return "", None
    try:
        main = driver.find_element(By.ID, "main-content").text
    except Exception:  # noqa: BLE001
        return "", None
    posted, time_str = None, None
    for line in driver.find_elements(By.CSS_SELECTOR, "div.article-metaline span.article-meta-value"):
        t = (line.text or "").strip()
        # 時間格式如 "Tue Mar  4 21:33:18 2025"
        try:
            posted = datetime.strptime(t, "%a %b %d %H:%M:%S %Y").replace(tzinfo=UTC)
            time_str = t
            break
        except ValueError:
            continue
    # 內文：切掉 metaline 表頭（作者/看板/標題/時間）+ 第一個「※ 發信站」之後的引言/簽名雜訊
    body = main
    if time_str and time_str in body:
        body = body.split(time_str, 1)[1]
    cut = body.find("※ 發信站")
    if cut > 0:
        body = body[:cut]
    return body.strip()[:5000], posted


def _normalize(p: dict) -> dict:
    return {
        "source": "ptt",
        "external_id": f"{p['board']}/{p['aid']}",
        "title": p["title"] or "(無標題)",
        "content": p.get("content", ""),
        "author": p["author"],
        "url": p["url"],
        "over_18": False,
        "score": _score_from_nrec(p["nrec"]),
        "num_comments": 0,
        "posted_at": p.get("posted_at") or datetime.now(UTC),
    }


def _get_with_retry(driver, url: str, *, tries: int = 4, wait: float = 8.0) -> bool:
    """載入頁面，失敗（斷網/renderer timeout）時指數退避重試。回傳是否成功。"""
    for i in range(tries):
        try:
            driver.get(url)
            return True
        except Exception as e:  # noqa: BLE001 — 斷網 ERR_NAME_NOT_RESOLVED / renderer timeout 都走重試
            msg = str(e).splitlines()[0][:90]
            print(f"  ⏳ 載入失敗（{i + 1}/{tries}）：{msg}，{wait:.0f}s 後重試", flush=True)
            time.sleep(wait)
            wait *= 2
    return False


def crawl_board(driver, board, max_pages, fetch_body, delay) -> list[dict]:
    """抓單一板的 AI 相關貼文（含內文）。回傳正規化 dict 清單。"""
    cands: list[dict] = []
    seen: set[str] = set()
    url = f"{_BASE}/bbs/{board}/index.html"
    for _pg in range(max_pages):
        if not _get_with_retry(driver, url):
            print(f"  ⚠️ {board} 重試仍失敗，跳到下一板", flush=True)
            break
        rows, prev = _parse_index(driver)
        for r in rows:
            if r["aid"] in seen or not is_ai_related(r["title"]):
                continue
            seen.add(r["aid"])
            cands.append(r)
        if not prev:
            break
        url = prev
        time.sleep(delay)

    if fetch_body:
        for p in cands:
            body, posted = _fetch_article(driver, p["url"])
            p["content"] = body
            p["posted_at"] = posted
            time.sleep(delay)
    print(f"  📋 {board}：AI 相關 {len(cands)} 篇", flush=True)
    return [_normalize(p) for p in cands]


async def _save(rows: list[dict]) -> None:
    # 每次 save 自建引擎並 dispose：本腳本逐板呼叫 asyncio.run()，每次都是新事件迴圈，
    # 若共用模組級全域引擎，其 asyncpg 連線綁在第一個（已關閉的）迴圈上 → 第二板起噴
    # 'NoneType' object has no attribute 'send'。每板一個短命引擎即可避開。
    from api.config import settings
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(settings.database_url)
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            stats = await upsert_posts(session, rows)
        print(f"💾 UPSERT：{stats}", flush=True)
    finally:
        await engine.dispose()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--boards", nargs="+", default=list(DEFAULT_BOARDS))
    ap.add_argument("--max-pages", type=int, default=40, help="每板往回翻幾頁 index")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--no-body", action="store_true", help="只抓標題列、不進文章頁（快但無內文/精確時間）")
    ap.add_argument("--delay", type=float, default=0.4, help="每次請求間隔秒（禮貌爬，避免限流）")
    args = ap.parse_args()

    print(f"🕷️ PTT 爬取：{args.boards}｜每板 {args.max_pages} 頁", flush=True)
    driver = _build_driver(args.headless)
    total = 0
    try:
        for board in args.boards:
            rows = crawl_board(driver, board, args.max_pages, not args.no_body, args.delay)
            if rows:
                asyncio.run(_save(rows))  # 每板即存，長跑抗中斷
                total += len(rows)
    finally:
        driver.quit()
    print(f"✅ 完成：本次 {total} 篇 AI 相關繁中 PTT 貼文", flush=True)


if __name__ == "__main__":
    main()
