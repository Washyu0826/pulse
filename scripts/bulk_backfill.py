"""
大量歷史回填（quality-first：保留 AI 關鍵字過濾）—— 多源寬日期，盡量把 AI 相關貼文灌滿 DB。

策略：
- HackerNews（Algolia）：**逐月切窗**回填。Algolia 每查詢上限 ~1000 筆，故把寬日期切成
  月窗逐一查，繞過單查詢截斷；UPSERT 以自然鍵 on-conflict 冪等，重疊/重跑安全。
- Dev.to：對整個範圍**只跑一次**（它從最新往回翻頁，逐月重跑會重複抓近期頁、浪費）。

每個月窗印出當下 DB posts 總數，方便看真實「新增」量（received 含已存在的更新，不等於新增）。

用法（務必帶 ENVIRONMENT=production 關掉 SQLAlchemy echo，否則 log 會被 SQL 灌爆）：
    cd api && ENVIRONMENT=production python ../scripts/bulk_backfill.py \
        --since 2020-01-01 --until 2026-05-01 --max-pages 10
"""
from __future__ import annotations

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

_SKIP_DEVTO = False  # 由 CLI --no-devto 覆寫


def _month_windows(since: datetime, until: datetime):
    """產生 [since, until) 的逐月 (start, end) 區間。"""
    cur = since.replace(day=1)
    while cur < until:
        if cur.month == 12:
            nxt = cur.replace(year=cur.year + 1, month=1)
        else:
            nxt = cur.replace(month=cur.month + 1)
        yield cur, min(nxt, until)
        cur = nxt


def _week_windows(since: datetime, until: datetime):
    """產生 [since, until) 的逐週 (start, end) 區間（密集期截斷回收用）。"""
    from datetime import timedelta

    cur = since
    while cur < until:
        nxt = cur + timedelta(days=7)
        yield cur, min(nxt, until)
        cur = nxt


def _windows(since: datetime, until: datetime, granularity: str):
    return (
        _week_windows(since, until) if granularity == "week" else _month_windows(since, until)
    )


async def _post_count() -> int:
    from sqlalchemy import text

    async with AsyncSessionLocal() as s:
        r = await s.execute(text("SELECT count(*) FROM posts"))
        return int(r.scalar() or 0)


async def main(since: datetime, until: datetime, max_pages: int, granularity: str = "month") -> None:
    start_count = await _post_count()
    print(
        f"🚀 bulk backfill {since.date()} ~ {until.date()}｜granularity={granularity}"
        f"｜起始 posts={start_count}",
        flush=True,
    )

    total_received = 0
    windows = list(_windows(since, until, granularity))
    for i, (w_since, w_until) in enumerate(windows, 1):
        rows: list[dict] = []
        async for post in crawl_hackernews(
            hits_per_page=100, since=w_since, until=w_until, max_pages=max_pages, keyword_only=True
        ):
            rows.append(post)
        if rows:
            async with AsyncSessionLocal() as session:
                await upsert_posts(session, rows)
        total_received += len(rows)
        cnt = await _post_count()
        print(
            f"  [{i:>3}/{len(windows)}] {w_since.date()}~{w_until.date()} "
            f"HN+{len(rows):>4} 篇｜DB posts={cnt}（+{cnt - start_count} 自起始）",
            flush=True,
        )

    # Dev.to：整段只跑一次（--no-devto 可跳過，例如截斷回收的二次掃不需重抓 Dev.to）
    if not _SKIP_DEVTO:
        print("📰 Dev.to 整段回填（單次）…", flush=True)
        devto_rows: list[dict] = []
        async for post in crawl_devto(
            per_page=100, since=since, until=until, max_pages=max_pages * 5, keyword_only=True
        ):
            devto_rows.append(post)
        if devto_rows:
            async with AsyncSessionLocal() as session:
                await upsert_posts(session, devto_rows)
        total_received += len(devto_rows)

    end_count = await _post_count()
    print(
        f"✅ 完成｜HN+Dev.to received={total_received}｜DB posts {start_count} → {end_count}"
        f"（淨新增 {end_count - start_count}）",
        flush=True,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--since", default="2020-01-01")
    p.add_argument("--until", default="2026-05-01")
    p.add_argument("--max-pages", type=int, default=10)
    p.add_argument("--granularity", choices=["month", "week"], default="month")
    p.add_argument("--no-devto", action="store_true", help="跳過 Dev.to（截斷回收二次掃用）")
    args = p.parse_args()
    _SKIP_DEVTO = args.no_devto
    s = datetime.fromisoformat(args.since).replace(tzinfo=UTC)
    u = datetime.fromisoformat(args.until).replace(tzinfo=UTC)
    asyncio.run(main(s, u, args.max_pages, args.granularity))
