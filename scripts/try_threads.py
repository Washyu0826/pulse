"""
本機驗證 Threads（Selenium）爬蟲：載入搜尋頁 → 抽貼文 → 印出來。

cookie 從 .env 的 THREADS_SESSIONID 讀（不用在指令列貼值）。建議用次要帳號。

預設「只印不寫 DB」+「開有頭瀏覽器」→ 純驗證爬蟲跑不跑得起來、抓不抓得到。
確認 OK 後再加 --save 寫進 DB，或直接去 Airflow UI unpause crawl_threads DAG。

前置：
    1. 本機已裝 Chrome（Selenium Manager 會自動抓 driver）
    2. .env 已填 THREADS_SESSIONID
    （--save 才需要：docker compose up -d db && cd api && uv run alembic upgrade head）

用法：
    cd api && uv run python ../scripts/try_threads.py                 # 看瀏覽器、只印
    cd api && uv run python ../scripts/try_threads.py --headless      # 不開視窗
    cd api && uv run python ../scripts/try_threads.py --max-posts 10
    cd api && uv run python ../scripts/try_threads.py --save          # 抓完寫進 DB
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Windows console 預設 cp950，印中文 / emoji 會 crash → 強制 UTF-8。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 企業 / 校園網路常做 TLS 攔截 → 改用 OS 信任庫（無攔截也安全）。best-effort。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "workers"))

from api.config import settings  # noqa: E402
from crawlers.threads import crawl_threads  # noqa: E402


async def main(args: argparse.Namespace) -> None:
    sessionid = settings.threads_sessionid or None
    if sessionid:
        print("🔑 已讀到 THREADS_SESSIONID（登入模式）")
    else:
        print("⚠️  .env 沒有 THREADS_SESSIONID → 未登入模式，多半會撞登入牆、抓很少")

    print(f"🌐 啟動瀏覽器（headless={args.headless}, scroll={args.scroll}）並抓取，請稍候…")
    rows: list[dict] = []
    async for row in crawl_threads(
        max_posts=args.max_posts,
        headless=args.headless,
        scroll_times=args.scroll,
        keyword_only=not args.all,
        sessionid=sessionid,
    ):
        rows.append(row)
        print(f"  • [{','.join(row['models']) or '-'}] @{row['author'] or '?'}: {row['title'][:60]}")

    print(f"\n📥 共抓到 {len(rows)} 則含模型關鍵字的貼文")
    if not rows:
        print("   （0 則通常是登入牆 / Meta 改版讓 selector 失效，不一定是程式壞 — 見 threads.py 註解）")

    if args.save and rows:
        from api.database import AsyncSessionLocal
        from api.services.posts import upsert_posts

        async with AsyncSessionLocal() as session:
            stats = await upsert_posts(session, rows)
        print(f"💾 已寫入 DB：{stats}")
    elif rows:
        print("ℹ️  （未寫 DB；要寫請加 --save）")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--headless", action="store_true", help="不開瀏覽器視窗（預設開，方便肉眼看）")
    parser.add_argument("--max-posts", type=int, default=15, help="每個查詢最多抽幾則")
    parser.add_argument("--scroll", type=int, default=3, help="每個查詢往下捲幾次（越多載越多）")
    parser.add_argument("--all", action="store_true", help="不過濾模型關鍵字，保留所有")
    parser.add_argument("--save", action="store_true", help="抓完寫進 DB（需 DB 已起、migrate 過）")
    asyncio.run(main(parser.parse_args()))
