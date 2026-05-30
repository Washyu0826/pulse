"""
批次跑情緒分析 → 寫進 sentiments 表（增量：只處理還沒分析的貼文）。

用 GPU（系統 Python 已有 torch+transformers）。Week 7 會被 Airflow DAG 取代。

用法（系統 Python，有 GPU）：
    python scripts/backfill_sentiments.py
"""
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
from api.models.sentiment import Sentiment  # noqa: E402
from api.services.sentiments import upsert_sentiments  # noqa: E402
from ml.sentiment import SentimentAnalyzer  # noqa: E402


async def main() -> None:
    # 1) 撈還沒分析情緒的貼文（左連 sentiments 找 NULL）
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post.id, Post.title, Post.content)
                .outerjoin(Sentiment, Sentiment.post_id == Post.id)
                .where(Sentiment.post_id.is_(None))
            )
        ).all()

    if not rows:
        print("✅ 所有貼文都已分析過情緒，無需處理。")
        return

    print(f"📥 {len(rows)} 篇待分析，載入模型…")
    analyzer = SentimentAnalyzer()
    print(f"   device={analyzer.device}，開始推論…")

    post_ids = [r.id for r in rows]
    texts = [f"{r.title or ''}. {r.content or ''}" for r in rows]
    results = analyzer.analyze_batch(texts, batch_size=64)  # GPU 批次

    out = [
        {
            "post_id": pid,
            "label": res.label,
            "score": round(res.score, 4),
            "p_positive": round(res.scores["positive"], 4),
            "p_neutral": round(res.scores["neutral"], 4),
            "p_negative": round(res.scores["negative"], 4),
            "confident": res.confident,
        }
        for pid, res in zip(post_ids, results)
    ]

    async with AsyncSessionLocal() as session:
        stats = await upsert_sentiments(session, out)

    print(f"💾 寫入 sentiments：{stats['upserted']} 筆")
    pos = sum(1 for r in results if r.label == "positive")
    neg = sum(1 for r in results if r.label == "negative")
    neu = len(results) - pos - neg
    print(f"📊 整體分佈：{pos}↑ positive · {neu}· neutral · {neg}↓ negative")


if __name__ == "__main__":
    asyncio.run(main())
