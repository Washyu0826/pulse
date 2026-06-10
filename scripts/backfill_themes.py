"""
批次跑主題分類 → 寫進 themes 表（增量：只處理還沒分類的貼文）。

用 GPU（系統 Python 已有 torch+transformers）。鏡像 backfill_sentiments.py。
只分類「已通過 DQC 且品質達標」的貼文（quality_score >= 門檻）—— 與看板/事件偵測一致，
不浪費算力在會被品質門檻擋掉的雜訊上。未跑過 DQC（quality_score IS NULL）的會等 DQC 後再分。

用法（系統 Python，有 GPU）：
    python scripts/backfill_themes.py
    python scripts/backfill_themes.py --min-quality 30
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
from api.models.posts import Post  # noqa: E402
from api.models.theme import Theme  # noqa: E402
from api.services.themes import upsert_themes  # noqa: E402
from ml.theme import ThemeClassifier  # noqa: E402
from sqlalchemy import select  # noqa: E402


async def _fetch_chunk(min_quality: int, chunk: int):
    """撈一批「已過 DQC、品質達標、尚未分類主題」的貼文（左連 themes 找 NULL）。"""
    async with AsyncSessionLocal() as session:
        return (
            await session.execute(
                select(Post.id, Post.title, Post.content)
                .outerjoin(Theme, Theme.post_id == Post.id)
                .where(Theme.post_id.is_(None))
                .where(Post.quality_score.is_not(None))
                .where(Post.quality_score >= min_quality)
                .where(~Post.quality_flags.contains(["DUPLICATE"]))
                .order_by(Post.fetched_at)
                .limit(chunk)
            )
        ).all()


async def main(min_quality: int, chunk: int = 2000) -> None:
    # 分塊處理 + 每塊即寫（可續跑、抗中斷）：大批量主題分類是 1~3 小時的 GPU 工作，
    # 整批最後才寫的話一中斷全失；改成每塊 upsert，下次重跑只接續未分類者。
    clf = None
    total = 0
    agg: dict[str, int] = {}
    while True:
        rows = await _fetch_chunk(min_quality, chunk)
        if not rows:
            break
        if clf is None:
            print("📥 載入主題模型…")
            clf = ThemeClassifier()
            print(f"   device={clf.device}，開始分塊推論（每塊 {chunk}）…")

        post_ids = [r.id for r in rows]
        texts = [f"{r.title or ''}. {r.content or ''}" for r in rows]
        results = clf.classify_batch(texts, batch_size=16)  # GPU 批次

        out = [
            {
                "post_id": pid,
                "label": res.label,
                "confidence": round(res.confidence, 4),
                "confident": res.confident,
            }
            for pid, res in zip(post_ids, results, strict=True)
        ]
        async with AsyncSessionLocal() as session:
            stats = await upsert_themes(session, out)
        total += stats["upserted"]
        for label, n in ThemeClassifier.distribution(results).items():
            agg[label] = agg.get(label, 0) + n
        print(f"   ＋{stats['upserted']} 筆（累計 {total}）", flush=True)

    if total == 0:
        print(f"✅ 沒有待分類的貼文（quality_score >= {min_quality}、非重複且未分類）。")
        return
    print(f"💾 寫入 themes 共 {total} 筆")
    print("📊 主題分佈：", dict(sorted(agg.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-quality", type=int, default=30,
        help="只分類 quality_score >= 此值的貼文（預設 30，與 ML pipeline 門檻一致）",
    )
    parser.add_argument("--chunk", type=int, default=2000, help="每塊處理筆數（即寫，可續跑）")
    args = parser.parse_args()
    asyncio.run(main(args.min_quality, args.chunk))
