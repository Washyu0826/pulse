"""
Facebook 爬蟲（Selenium 真瀏覽器）—— 抓台灣 AI 社團/專頁的繁中貼文寫進 DB。

⚠️ 風險與限制（誠實聲明）：
- FB 對自動化偵測是 Meta 全家最嚴：**務必用次要帳號的 cookie**（FB_C_USER + FB_XS）。
  若載入後跳 checkpoint / 登入頁，本腳本會立刻中止並提示（代表 cookie 失效或被盯上）。
- FB 的 DOM 是混淆 class 名 + 高頻改版 → 用 role 屬性選擇器（div[role=article]）盡量穩，
  但仍屬「易壞」爬蟲；壞了優先檢查 selector。
- 動態牆只能 scroll 載入，每目標每輪數十～數百則；FB 顯示相對時間（「3小時」），
  發文精確時間難取 → posted_at 以抓取當下代替（限制已知）。

用法（先在 .env 填 FB_C_USER / FB_XS；目標給社團/專頁網址或路徑）：
    python scripts/crawl_facebook.py --targets groups/123456789 --scroll 10 --headless
    python scripts/crawl_facebook.py --targets https://www.facebook.com/groups/aitaiwan groups/987 --headless
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
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
from crawlers.keywords import is_ai_related, looks_simplified  # noqa: E402

_BASE = "https://www.facebook.com"
# 貼文 permalink 樣式（feed 內連結常帶追蹤參數，取 id 部分當 external_id）
_PERMALINK_RES = (
    re.compile(r"/groups/[^/]+/(?:permalink|posts)/(\d+)"),
    re.compile(r"/posts/(pfbid\w+|\d+)"),
    re.compile(r"story_fbid=(pfbid\w+|\d+)"),
    re.compile(r"/(?:videos|reel)/(\d+)"),
)


def _load_dotenv() -> None:
    """讀 .env 注入環境變數（不覆寫既有值）。FB cookie 不經 api.config，直接讀 env。"""
    import os

    env = _ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        v = v.split("  #")[0].strip()  # 去行尾註解
        os.environ.setdefault(k.strip(), v)


def _get_cookies() -> tuple[str, str]:
    import os

    _load_dotenv()
    c_user = os.environ.get("FB_C_USER", "").strip()
    xs = os.environ.get("FB_XS", "").strip()
    if not c_user or not xs:
        print("❌ .env 缺 FB_C_USER / FB_XS（兩者都要）。瀏覽器 F12 → Application → Cookies → facebook.com 取得。", file=sys.stderr)
        raise SystemExit(1)
    return c_user, xs


def _build_driver(headless: bool, c_user: str, xs: str):
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options

    o = Options()
    if headless:
        o.add_argument("--headless=new")
    o.add_argument("--no-sandbox")
    o.add_argument("--disable-dev-shm-usage")
    o.add_argument("--disable-gpu")
    o.add_argument("--window-size=1280,2400")
    o.add_argument("--lang=zh-TW")
    o.add_argument("--log-level=3")
    o.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    d = webdriver.Chrome(options=o)
    d.set_page_load_timeout(45)
    # 先落地 facebook.com 才能設同網域 cookie，再注入登入 cookie
    d.get(_BASE)
    for name, value in (("c_user", c_user), ("xs", xs)):
        d.add_cookie({"name": name, "value": value, "domain": ".facebook.com", "path": "/", "secure": True})
    return d


def _get_with_retry(driver, url: str, *, tries: int = 4, wait: float = 8.0) -> bool:
    for i in range(tries):
        try:
            driver.get(url)
            return True
        except Exception as e:  # noqa: BLE001 — 斷網/renderer timeout 都重試
            msg = str(e).splitlines()[0][:90]
            print(f"  ⏳ 載入失敗（{i + 1}/{tries}）：{msg}，{wait:.0f}s 後重試", flush=True)
            time.sleep(wait)
            wait *= 2
    return False


def _check_logged_in(driver) -> None:
    """checkpoint / 被導去登入頁 = cookie 失效或帳號被盯 → 立刻中止，避免越爬越糟。"""
    url = driver.current_url
    if "checkpoint" in url or "/login" in url:
        print(f"❌ 被導向 {url} —— cookie 失效或帳號被 FB 盯上。請換 cookie / 改用次要帳號。", file=sys.stderr)
        raise SystemExit(2)


def _norm_target(t: str) -> str:
    t = t.strip()
    if t.startswith("http"):
        return t
    return f"{_BASE}/{t.lstrip('/')}"


def _extract_external_id(article) -> str | None:
    """從貼文卡片內的連結找 permalink id。找不到回 None（呼叫端再用內容 hash 兜底）。"""
    try:
        links = article.find_elements("css selector", "a[href]")
    except Exception:  # noqa: BLE001
        return None
    for a in links:
        href = a.get_attribute("href") or ""
        for rx in _PERMALINK_RES:
            m = rx.search(href)
            if m:
                return m.group(1)
    return None


def _harvest(driver, target_label: str, max_posts: int) -> list[dict]:
    """掃目前頁面上的貼文卡片 → 正規化 dict。以 external_id 去重由呼叫端做。"""
    out: list[dict] = []
    try:
        articles = driver.find_elements("css selector", "div[role='article']")
    except Exception:  # noqa: BLE001
        return out
    for art in articles[: max_posts * 3]:  # 卡片含 UI 雜訊，多掃一些再過濾
        try:
            text = (art.text or "").strip()
        except Exception:  # noqa: BLE001
            continue
        if len(text) < 30:
            continue  # UI 殘片
        if looks_simplified(text):
            continue  # 擋簡體（保台灣繁中訊號）
        if not is_ai_related(text):
            continue
        ext = _extract_external_id(art)
        if not ext:
            ext = "h" + hashlib.md5(text[:200].encode("utf-8")).hexdigest()[:16]
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        author = lines[0][:80] if lines else ""
        body = "\n".join(lines[1:])[:5000] if len(lines) > 1 else text[:5000]
        title = (body.splitlines()[0] if body else text)[:80]
        out.append(
            {
                "source": "facebook",
                "external_id": f"{target_label}/{ext}",
                "title": title or "(無標題)",
                "content": body,
                "author": author,
                "url": f"{_BASE}/{ext}" if not ext.startswith("h") else None,
                "over_18": False,
                "score": 0,
                "num_comments": 0,
                # FB 牆上只有相對時間（「3 小時」），精確發文時間難取 → 以抓取時間代替（已知限制）
                "posted_at": datetime.now(UTC),
            }
        )
    return out


def crawl_target(driver, target: str, scroll: int, max_posts: int, delay: float) -> list[dict]:
    url = _norm_target(target)
    label = re.sub(r"https?://(www\.)?facebook\.com/", "", url).strip("/") or "feed"
    if not _get_with_retry(driver, url):
        print(f"  ⚠️ {label} 載入失敗，跳過", flush=True)
        return []
    _check_logged_in(driver)
    time.sleep(3)

    seen: dict[str, dict] = {}
    for _ in range(scroll):
        for row in _harvest(driver, label, max_posts):
            seen.setdefault(row["external_id"], row)
        if len(seen) >= max_posts:
            break
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(delay)
    rows = list(seen.values())[:max_posts]
    print(f"  📋 {label}：AI 相關繁中 {len(rows)} 則", flush=True)
    return rows


async def _save(rows: list[dict]) -> None:
    # 每次 save 自建短命引擎（見 crawl_ptt.py 同段註解）：逐目標 asyncio.run() 會換新事件迴圈，
    # 共用全域引擎會在第二個目標起噴 asyncpg 'NoneType'.send。
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
    ap = argparse.ArgumentParser(description="FB 社團/專頁爬蟲（需 .env FB_C_USER/FB_XS，建議次要帳號）")
    ap.add_argument("--targets", nargs="+", required=True, help="社團/專頁網址或路徑（如 groups/123456）")
    ap.add_argument("--scroll", type=int, default=10, help="每目標往下捲幾次")
    ap.add_argument("--max-posts", type=int, default=80, help="每目標最多收幾則")
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--delay", type=float, default=2.5, help="每次捲動間隔秒（禮貌爬）")
    args = ap.parse_args()

    c_user, xs = _get_cookies()
    print(f"🕷️ FB 爬取 {len(args.targets)} 個目標（scroll={args.scroll}）", flush=True)
    driver = _build_driver(args.headless, c_user, xs)
    total = 0
    try:
        for t in args.targets:
            rows = crawl_target(driver, t, args.scroll, args.max_posts, args.delay)
            if rows:
                asyncio.run(_save(rows))  # 每目標即存，抗中斷
                total += len(rows)
            time.sleep(args.delay * 2)  # 目標間多歇一下，降低被盯機率
    finally:
        driver.quit()
    print(f"✅ 完成：本次 {total} 則 AI 相關繁中 FB 貼文", flush=True)


if __name__ == "__main__":
    main()
