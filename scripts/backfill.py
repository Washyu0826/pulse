"""
回填指定日期範圍的歷史資料（預設 2026-04-01 ~ 2026-06-01）。

- HackerNews：用 Algolia numericFilters 精準抓日期範圍 + 多頁。
- Dev.to：往回翻頁回填到 since。
- Hugging Face：拉較大 limit（每 org 最新 N 筆，再由 published_at 過濾）。

零 key。用法：
    cd api && uv run python ../scripts/backfill.py --since 2026-04-01 --until 2026-06-01
"""
import argparse
import asyncio
import sys
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

from api.database import AsyncSessionLocal  # noqa: E402
from api.services.posts import upsert_posts  # noqa: E402
from crawlers.devto import crawl_devto  # noqa: E402
from crawlers.hackernews import crawl_hackernews  # noqa: E402


async def main(since: datetime, until: datetime, max_pages: int) -> None:
    rows: list[dict] = []

    # HackerNews（日期範圍精準）
    async for post in crawl_hackernews(
        hits_per_page=100, since=since, until=until, max_pages=max_pages
    ):
        rows.append(post)
    hn = len(rows)

    # Dev.to（往回翻頁回填到 since；until 由爬蟲內部過濾，與 HN 對稱）
    async for post in crawl_devto(per_page=100, since=since, until=until, max_pages=max_pages):
        rows.append(post)
    devto = len(rows) - hn

    print(f"📥 回填 {since.date()} ~ {until.date()}：HN {hn} 篇、Dev.to {devto} 篇，共 {len(rows)} 篇")

    async with AsyncSessionLocal() as session:
        stats = await upsert_posts(session, rows)
    print("💾 UPSERT 統計：", stats)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", default="2026-04-01")
    parser.add_argument("--until", default="2026-06-01")
    parser.add_argument("--max-pages", type=int, default=10)
    args = parser.parse_args()
    since = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
    until = datetime.fromisoformat(args.until).replace(tzinfo=UTC)
    asyncio.run(main(since, until, args.max_pages))
