"""
回填清洗既有 Threads 貼文的 content/title —— 剝掉 UI chrome（作者名 / 日期 / 相對時間 /
互動計數 / 分頁 / 翻譯），對齊新爬蟲的 clean_thread_text（content-quality backlog #1）。

既有髒 content 是「用髒文字算過 DQC/主題/熱詞」的，清洗後需讓下游重算：
  - content/title 寫回乾淨值。
  - dq_processed_at=NULL、quality_score=NULL、quality_flags='{}' → 下次 DQC 重評分乾淨文字。
    （主題/熱詞回填腳本本就只挑 quality_score 達標的，重評後會自然接續重算。）

預設 --dry-run：只印「清洗前/後」對照，不寫 DB。確認沒誤刪真內文後，加 --apply 實際寫回。

用法（系統 Python，連 docker pulse-db，DATABASE_URL 在 .env，port 5433）：
    python scripts/backfill_threads_clean.py                 # dry-run，印對照
    python scripts/backfill_threads_clean.py --days 2        # 只看近 2 天
    python scripts/backfill_threads_clean.py --apply         # 實際寫回 + 重置 DQC
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
sys.path.insert(0, str(_ROOT / "workers"))

from api.database import AsyncSessionLocal  # noqa: E402
from crawlers.threads_clean import clean_thread_text  # noqa: E402
from sqlalchemy import bindparam, text  # noqa: E402

_SELECT = text(
    "SELECT id, title, content FROM posts "
    "WHERE source='threads' "
    "AND (:all_rows OR fetched_at >= now() - make_interval(days => :days)) "
    "ORDER BY id"
)

# 寫回：乾淨 content/title + 重置 DQC（讓下游用乾淨文字重評分/重分類/重抽熱詞）。
_UPDATE = text(
    "UPDATE posts SET content=:content, title=:title, "
    "quality_score=NULL, quality_flags='{}', dq_processed_at=NULL "
    "WHERE id=:id"
).bindparams(bindparam("id"))


def _new_title(clean_content: str) -> str:
    """與 normalize_thread_post 一致：取乾淨內文前 120 字當標題，空則用占位。"""
    return clean_content[:120] or "(Threads 貼文)"


async def main(args: argparse.Namespace) -> None:
    all_rows = args.days <= 0
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(_SELECT, {"all_rows": all_rows, "days": args.days})
        ).all()

    scope = "全部" if all_rows else f"近 {args.days} 天"
    print(f"📥 Threads 貼文（{scope}）：{len(rows)} 筆")

    changed: list[dict] = []
    for r in rows:
        old_content = r.content or ""
        new_content = clean_thread_text(old_content)
        new_title = _new_title(new_content)
        if new_content != old_content or (r.title or "") != new_title:
            changed.append(
                {"id": r.id, "title": new_title, "content": new_content,
                 "old_content": old_content, "old_title": r.title or ""}
            )

    print(f"🧹 需清洗：{len(changed)} / {len(rows)} 筆\n")

    # 印對照（dry-run 全印；apply 也印前幾筆當紀錄）。標出「清洗後變空」的可疑筆。
    sample = changed if args.dry_run else changed[: args.show]
    empties = [c for c in changed if not c["content"].strip()]
    for i, c in enumerate(sample[: args.show if args.dry_run else len(sample)], 1):
        print(f"──── #{i}  post_id={c['id']} ────")
        print(f"  [前] {c['old_content'][:240]!r}")
        print(f"  [後] {c['content'][:240]!r}")
        print()
    if len(changed) > args.show:
        print(f"…（其餘 {len(changed) - args.show} 筆未印）\n")

    if empties:
        print(f"⚠️ 清洗後變空白的有 {len(empties)} 筆（post_id={[c['id'] for c in empties][:20]}）"
              " —— 這些是純 chrome 卡片，清洗正確；DQC 會以 TOO_SHORT 擋掉。\n")

    if args.dry_run:
        print("（dry-run：未寫 DB。確認對照無誤後加 --apply 實際寫回。）")
        return

    payload = [{"id": c["id"], "title": c["title"], "content": c["content"]} for c in changed]
    if not payload:
        print("✅ 無需寫回。")
        return
    async with AsyncSessionLocal() as session:
        for chunk_start in range(0, len(payload), 500):
            await session.execute(_UPDATE, payload[chunk_start : chunk_start + 500])
        await session.commit()
    print(f"💾 已寫回 {len(payload)} 筆乾淨 content/title，並重置 DQC（dq_processed_at=NULL）。")
    print("   後續：跑 DQC 重評分 → backfill_themes / backfill_keywords 重算下游。")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=1,
                   help="只處理近 N 天的 Threads 貼文（預設 1；<=0 表示全部）")
    p.add_argument("--apply", dest="dry_run", action="store_false",
                   help="實際寫回 DB（預設 dry-run 只印對照）")
    p.add_argument("--show", type=int, default=15, help="印幾筆對照樣本")
    p.set_defaults(dry_run=True)
    asyncio.run(main(p.parse_args()))
