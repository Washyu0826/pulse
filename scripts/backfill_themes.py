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

from sqlalchemy import select  # noqa: E402

from api.database import AsyncSessionLocal  # noqa: E402
from api.models.posts import Post  # noqa: E402
from api.models.theme import Theme  # noqa: E402
from api.services.themes import upsert_themes  # noqa: E402
from ml.theme import ThemeClassifier  # noqa: E402


async def main(min_quality: int) -> None:
    # 1) 撈「已通過 DQC、品質達標、尚未分類主題」的貼文（左連 themes 找 NULL）
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post.id, Post.title, Post.content)
                .outerjoin(Theme, Theme.post_id == Post.id)
                .where(Theme.post_id.is_(None))
                .where(Post.quality_score.is_not(None))
                .where(Post.quality_score >= min_quality)
            )
        ).all()

    if not rows:
        print(f"✅ 沒有待分類的貼文（quality_score >= {min_quality} 且未分類）。")
        return

    print(f"📥 {len(rows)} 篇待分類，載入模型…")
    clf = ThemeClassifier()
    print(f"   device={clf.device}，開始推論…")

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
        for pid, res in zip(post_ids, results)
    ]

    async with AsyncSessionLocal() as session:
        stats = await upsert_themes(session, out)

    print(f"💾 寫入 themes：{stats['upserted']} 筆")
    dist = ThemeClassifier.distribution(results)
    print("📊 主題分佈：", dict(sorted(dist.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-quality", type=int, default=30,
        help="只分類 quality_score >= 此值的貼文（預設 30，與 ML pipeline 門檻一致）",
    )
    asyncio.run(main(parser.parse_args().min_quality))
