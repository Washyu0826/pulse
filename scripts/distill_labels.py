"""
產 silver labels —— 用地端 Qwen2.5（Ollama）把中文貼文預標，供微調小模型（Phase 3）。

silver labels 只供「訓練增強」，不進測試集（測試集只用人工驗證的 gold，見 annotation-guidelines.md）。
可續跑：自動跳過 silver JSONL 裡已標過 (post_id) 的貼文。

前置：Ollama 服務開著且已 pull 模型（預設 qwen2.5:7b）。
用法（系統 Python；需 httpx + Ollama）：
    # 對中文貼文產情緒 silver labels（抽最近 90 天、上限 2000 篇）
    python scripts/distill_labels.py --task sentiment --zh --limit 2000 --days 90
    # 主題 silver labels
    python scripts/distill_labels.py --task theme --zh --limit 2000 --days 90
"""
import argparse
import asyncio
import re
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

from api.database import AsyncSessionLocal  # noqa: E402
from api.models.posts import Post  # noqa: E402
from ml.annotation import append_jsonl, load_jsonl  # noqa: E402
from ml.distill import Distiller  # noqa: E402
from sqlalchemy import select  # noqa: E402

_CJK_RE = re.compile(r"[一-鿿]")
_TEXT_SNIPPET = 1000


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


async def _fetch_posts(days: int, min_quality: int, limit: int) -> list[dict]:
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post.id, Post.source, Post.title, Post.content)
                .where((Post.quality_score.is_(None)) | (Post.quality_score >= min_quality))
                .where(Post.posted_at >= datetime.now(UTC) - timedelta(days=days))
                .order_by(Post.posted_at.desc())
                .limit(limit)
            )
        ).all()
    return [
        {"id": r.id, "source": r.source, "title": r.title or "", "content": r.content or ""}
        for r in rows
    ]


async def main_async(args: argparse.Namespace) -> None:
    out = args.out or _ROOT / "data" / "silver" / f"silver_{args.task}.jsonl"
    done = {r["post_id"] for r in load_jsonl(out)}
    print(f"📂 silver set：{out}（已標 {len(done)} 筆）")

    posts = await _fetch_posts(args.days, args.min_quality, args.limit)
    if args.zh:
        posts = [p for p in posts if _cjk_ratio(f"{p['title']}{p['content']}") >= 0.20]
    posts = [p for p in posts if p["id"] not in done]
    if not posts:
        print("✅ 沒有待標貼文（都標過了或抽不到）。")
        return

    print(f"🤖 待標 {len(posts)} 篇，task={args.task}，呼叫本地 Qwen…")
    distiller = Distiller()
    labeled = skipped = 0
    import httpx

    async with httpx.AsyncClient(timeout=distiller.timeout) as client:
        for i, post in enumerate(posts, 1):
            text = f"{post['title']}. {post['content']}"[:_TEXT_SNIPPET]
            label = await distiller.label(text, args.task, client=client)
            if label is None:
                skipped += 1
                continue
            append_jsonl(
                out,
                {
                    "post_id": post["id"],
                    "source": post["source"],
                    "task": args.task,
                    "label": label,
                    "text": text[:600],
                    "model": distiller.model,
                    "labeled_at": datetime.now(UTC).isoformat(),
                },
            )
            labeled += 1
            if i % 50 == 0:
                print(f"   …{i}/{len(posts)}（已寫 {labeled}、略過 {skipped}）")

    print(f"💾 完成：silver 新增 {labeled} 筆、解析失敗略過 {skipped} 筆 → {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Qwen 蒸餾產 silver labels")
    ap.add_argument("--task", choices=["sentiment", "theme"], required=True)
    ap.add_argument("--out", type=Path, default=None, help="silver JSONL 路徑（預設 data/silver/silver_<task>.jsonl）")
    ap.add_argument("--limit", type=int, default=2000, help="最多抽幾篇")
    ap.add_argument("--days", type=int, default=90, help="只抽最近 N 天")
    ap.add_argument("--min-quality", type=int, default=30, help="只標品質分 >= 此值（NULL 也納入）")
    ap.add_argument("--zh", action="store_true", help="只標中文為主的貼文（CJK 比 >= 20%%）")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
