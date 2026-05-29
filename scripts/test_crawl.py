"""
手動測試腳本：爬資料 → UPSERT 進 DB → 印統計。

支援多來源：
    --source hackernews   （預設，零 key）
    --source reddit        （需 .env 的 Reddit credential）

Week 1 驗收用（之後 Week 6 會被 Airflow DAG 取代）。

前置：
    1. docker compose up -d db
    2. cd api && uv run alembic upgrade head
    3. python scripts/seed_models.py

用法：
    cd api && uv run python ../scripts/test_crawl.py --source hackernews --limit 50
    cd api && uv run python ../scripts/test_crawl.py --source reddit --subreddits ClaudeAI
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Windows console 預設 cp950，印中文 / emoji 會 crash → 強制 UTF-8。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 企業 / 校園網路常做 TLS 攔截，根憑證在 OS 信任庫但不在 Python 的。
# truststore 讓 Python 改用 OS 信任庫（無攔截的網路也安全）。best-effort。
try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "workers"))

from api.config import settings  # noqa: E402
from api.database import AsyncSessionLocal  # noqa: E402
from api.services.posts import upsert_posts  # noqa: E402
from crawlers.hackernews import crawl_hackernews  # noqa: E402
from crawlers.reddit import DEFAULT_SUBREDDITS, crawl_reddit  # noqa: E402


async def _collect_reddit(subreddits: list[str], limit: int, keyword_only: bool) -> list[dict]:
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        print("❌ 缺 Reddit credential，請在 .env 填 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET")
        sys.exit(1)
    rows = []
    async for post in crawl_reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        subreddits=subreddits,
        limit=limit,
        keyword_only=keyword_only,
    ):
        rows.append(post)
    return rows


async def _collect_hackernews(limit: int, keyword_only: bool) -> list[dict]:
    rows = []
    async for post in crawl_hackernews(hits_per_page=limit, keyword_only=keyword_only):
        rows.append(post)
    return rows


async def main(args: argparse.Namespace) -> None:
    if args.source == "reddit":
        rows = await _collect_reddit(args.subreddits, args.limit, keyword_only=not args.all)
    else:
        rows = await _collect_hackernews(args.limit, keyword_only=not args.all)

    print(f"📥 [{args.source}] 抓到 {len(rows)} 篇含模型關鍵字的貼文")

    async with AsyncSessionLocal() as session:
        stats = await upsert_posts(session, rows)

    print("💾 UPSERT 統計：")
    print(f"   received     = {stats['received']}")
    print(f"   skipped      = {stats['skipped']}")
    print(f"   upserted     = {stats['upserted']}")
    print(f"   associations = {stats['associations']}")

    dist: dict[str, int] = {}
    for r in rows:
        for slug in r["models"]:
            dist[slug] = dist.get(slug, 0) + 1
    print("📊 模型命中分佈：", dict(sorted(dist.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source", choices=["hackernews", "reddit"], default="hackernews",
        help="資料來源（預設 hackernews，零 key）",
    )
    parser.add_argument(
        "--subreddits", nargs="*", default=list(DEFAULT_SUBREDDITS),
        help="（reddit 用）要抓的 subreddit",
    )
    parser.add_argument(
        "--limit", type=int, default=50,
        help="每個 subreddit / 每個關鍵字抓幾篇",
    )
    parser.add_argument("--all", action="store_true", help="不過濾關鍵字，保留所有")
    asyncio.run(main(parser.parse_args()))
