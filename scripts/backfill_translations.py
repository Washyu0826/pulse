"""
批次翻譯英文貼文 → 繁中（地端 Ollama qwen2.5）→ translations 表。增量：只翻沒譯過的。

只翻英文貼（HN/Dev.to；CJK 比例低）；中文貼（Threads）跳過。預設只翻近期高品質貼（與 feed 一致），
避免一次翻 5000 篇燒太久。需 Ollama 服務在跑（http://127.0.0.1:11434）。

用法（系統 Python，已裝 httpx+opencc）：
    python scripts/backfill_translations.py --days 30 --limit 300
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
from api.services.translations import upsert_translations  # noqa: E402
from ml.translate import Translator, needs_translation  # noqa: E402
from sqlalchemy import text  # noqa: E402

_SQL = text(
    "SELECT p.id, p.title, p.content "
    "FROM posts p LEFT JOIN translations t ON t.post_id = p.id "
    "WHERE t.post_id IS NULL "
    "AND (p.quality_score IS NULL OR p.quality_score >= 30) "
    "AND NOT (p.quality_flags @> ARRAY['DUPLICATE']) "
    "AND p.posted_at >= now() - make_interval(days => :days) "
    "ORDER BY p.posted_at DESC LIMIT :limit"
)


async def main(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        rows = (await session.execute(_SQL, {"days": args.days, "limit": args.limit})).all()

    # 只留需要翻的（英文）；中文貼跳過。
    todo = [(r.id, r.title or "", (r.content or "")[:200]) for r in rows if needs_translation(r.title or "")]
    print(f"📥 {len(rows)} 篇待查，其中 {len(todo)} 篇英文需翻譯")
    if not todo:
        print("✅ 沒有需要翻譯的貼文。")
        return

    import httpx

    tr = Translator()
    out: list[dict] = []
    async with httpx.AsyncClient(timeout=120.0) as client:
        for i, (pid, title, snippet) in enumerate(todo, 1):
            title_zh = await tr.translate(title, client=client)
            snippet_zh = await tr.translate(snippet, client=client) if snippet else None
            out.append({"post_id": pid, "title_zh": title_zh, "snippet_zh": snippet_zh})
            if i % 10 == 0 or i == len(todo):
                print(f"  …{i}/{len(todo)}")

    async with AsyncSessionLocal() as session:
        stats = await upsert_translations(session, out)
    print(f"💾 寫入 translations：{stats['upserted']} 筆")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30, help="只翻近 N 天的貼文")
    p.add_argument("--limit", type=int, default=300, help="單次最多翻幾篇（控時間）")
    asyncio.run(main(p.parse_args()))
