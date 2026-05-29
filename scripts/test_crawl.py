"""
手動測試腳本：爬 Reddit → UPSERT 進 DB → 印統計。

Week 1 驗收用（之後 Week 6 會被 Airflow DAG 取代）。

前置：
    1. docker compose up -d db   （Postgres 起來）
    2. cd api && uv run alembic upgrade head   （建表）
    3. python scripts/seed_models.py            （seed 6 模型）
    4. .env 填好 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT

用法：
    cd api && uv run python ../scripts/test_crawl.py --subreddits ClaudeAI --limit 50
"""
import argparse
import asyncio
import sys
from pathlib import Path

# Windows console 預設 cp950，印中文 / emoji 會 crash → 強制 UTF-8。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "workers"))

from api.config import settings  # noqa: E402
from api.database import AsyncSessionLocal  # noqa: E402
from api.services.posts import upsert_posts  # noqa: E402
from crawlers.reddit import DEFAULT_SUBREDDITS, crawl_reddit  # noqa: E402


async def main(subreddits: list[str], limit: int, keyword_only: bool) -> None:
    if not settings.reddit_client_id or not settings.reddit_client_secret:
        print("❌ 缺 Reddit credential，請在 .env 填 REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET")
        sys.exit(1)

    rows: list[dict] = []
    async for post in crawl_reddit(
        client_id=settings.reddit_client_id,
        client_secret=settings.reddit_client_secret,
        user_agent=settings.reddit_user_agent,
        subreddits=subreddits,
        limit=limit,
        keyword_only=keyword_only,
    ):
        rows.append(post)

    print(f"📥 抓到 {len(rows)} 篇含模型關鍵字的貼文")

    async with AsyncSessionLocal() as session:
        stats = await upsert_posts(session, rows)

    print("💾 UPSERT 統計：")
    print(f"   received     = {stats['received']}")
    print(f"   skipped      = {stats['skipped']}")
    print(f"   upserted     = {stats['upserted']}")
    print(f"   associations = {stats['associations']}")

    # 簡單分佈：每個模型命中幾篇
    dist: dict[str, int] = {}
    for r in rows:
        for slug in r["models"]:
            dist[slug] = dist.get(slug, 0) + 1
    print("📊 模型命中分佈：", dict(sorted(dist.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--subreddits", nargs="*", default=list(DEFAULT_SUBREDDITS),
        help="要抓的 subreddit（預設全部）",
    )
    parser.add_argument("--limit", type=int, default=50, help="每個 subreddit 抓幾篇")
    parser.add_argument(
        "--all", action="store_true", help="不過濾關鍵字，保留所有貼文",
    )
    args = parser.parse_args()
    asyncio.run(main(args.subreddits, args.limit, keyword_only=not args.all))
