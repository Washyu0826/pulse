"""
算「本週熱詞」→（之後寫進 trending_keywords 表）。先 print 驗證品質。

近期窗（預設 7 天）vs 基線窗（預設 30 天，含近期）→ log-odds 趨勢 → top N 熱詞。
只看高品質、非重複貼文（與 feed 一致）。中英混雜由 ml.keywords 處理（OpenCC+jieba）。

用法（系統 Python，已裝 jieba+opencc）：
    python scripts/backfill_keywords.py
    python scripts/backfill_keywords.py --recent 7 --baseline 30 --top 25
"""
import argparse
import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

from api.database import AsyncSessionLocal  # noqa: E402
from api.services.trending import replace_trending  # noqa: E402
from ml.keywords import compute_trending  # noqa: E402
from sqlalchemy import text  # noqa: E402

_SQL = text(
    "SELECT coalesce(title,'') || '. ' || coalesce(content,'') "
    "FROM posts "
    "WHERE (quality_score IS NULL OR quality_score >= 30) "
    "AND NOT (quality_flags @> ARRAY['DUPLICATE']) "
    "AND posted_at >= now() - make_interval(days => :days)"
)


async def _fetch(session, days: int) -> list[str]:
    rows = await session.execute(_SQL, {"days": days})
    return [r[0] for r in rows]


async def main(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        recent = await _fetch(session, args.recent)
        baseline = await _fetch(session, args.baseline)

    print(f"📥 近 {args.recent} 天 {len(recent)} 篇 · 基線 {args.baseline} 天 {len(baseline)} 篇")
    if not recent:
        print("⚠️ 近期窗無貼文（資料可能不夠新）。")
        return

    kws = compute_trending(recent, baseline, top_n=args.top, min_recent=args.min_recent)
    print(f"\n🔥 本週熱詞 top {len(kws)}：")
    for i, kw in enumerate(kws, 1):
        print(f"  {i:2}. {kw['term']:16} z={kw['z']:6.2f}  (近期 {kw['recent_count']} 篇)")

    if not args.dry_run:
        rows = [
            {"term": kw["term"], "rank": i, "z": kw["z"], "recent_count": kw["recent_count"]}
            for i, kw in enumerate(kws, 1)
        ]
        async with AsyncSessionLocal() as session:
            n = await replace_trending(session, rows)
        print(f"\n💾 寫入 trending_keywords：{n} 筆")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--recent", type=int, default=7, help="近期窗天數")
    p.add_argument("--baseline", type=int, default=30, help="基線窗天數（含近期）")
    p.add_argument("--top", type=int, default=25)
    p.add_argument("--min-recent", type=int, default=5, help="近期最低文章數（殺噪音）")
    p.add_argument("--dry-run", action="store_true", help="只印不寫 DB")
    asyncio.run(main(p.parse_args()))
