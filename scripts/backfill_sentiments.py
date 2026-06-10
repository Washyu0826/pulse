"""
批次跑情緒分析 → 寫進 sentiments 表（增量：只處理還沒分析的貼文）。

用 GPU（系統 Python 已有 torch+transformers）。Week 7 會被 Airflow DAG 取代。

用法（系統 Python，有 GPU）：
    python scripts/backfill_sentiments.py
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
from api.models.sentiment import Sentiment  # noqa: E402
from api.services.sentiments import upsert_sentiments  # noqa: E402
from ml.sentiment import SentimentAnalyzer  # noqa: E402
from sqlalchemy import select  # noqa: E402


def _pending_sentiment_stmt(min_quality: int):
    return (
        select(Post.id, Post.title, Post.content)
        .outerjoin(Sentiment, Sentiment.post_id == Post.id)
        .where(Sentiment.post_id.is_(None))
        .where(Post.quality_score.is_not(None))
        .where(Post.quality_score >= min_quality)
        .where(~Post.quality_flags.contains(["DUPLICATE"]))
        .order_by(Post.fetched_at)
    )


async def _fetch_chunk(min_quality: int, chunk: int):
    """撈一批「已過 DQC、品質達標、非重複、尚未分析情緒」的貼文。"""
    async with AsyncSessionLocal() as session:
        return (await session.execute(_pending_sentiment_stmt(min_quality).limit(chunk))).all()


async def main(min_quality: int, chunk: int = 2000, batch_size: int = 64) -> None:
    analyzer = None
    total = 0
    pos = neg = neu = 0

    while True:
        rows = await _fetch_chunk(min_quality, chunk)
        if not rows:
            break
        if analyzer is None:
            print("📥 載入情緒模型…")
            analyzer = SentimentAnalyzer()
            print(f"   device={analyzer.device}，chunk={chunk}，batch_size={batch_size}")

        post_ids = [r.id for r in rows]
        texts = [f"{r.title or ''}. {r.content or ''}" for r in rows]
        results = analyzer.analyze_batch(texts, batch_size=batch_size)  # GPU 批次

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
            for pid, res in zip(post_ids, results, strict=True)
        ]

        async with AsyncSessionLocal() as session:
            stats = await upsert_sentiments(session, out)

        total += stats["upserted"]
        pos += sum(1 for r in results if r.label == "positive")
        neg += sum(1 for r in results if r.label == "negative")
        neu += sum(1 for r in results if r.label == "neutral")
        print(f"   ＋{stats['upserted']} 筆（累計 {total}）", flush=True)

    if total == 0:
        print(f"✅ 沒有待分析情緒的貼文（quality_score >= {min_quality} 且非重複）。")
        return

    print(f"💾 寫入 sentiments 共 {total} 筆")
    print(f"📊 整體分佈：{pos}↑ positive · {neu}· neutral · {neg}↓ negative")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--min-quality",
        type=int,
        default=30,
        help="只分析 quality_score >= 此值且非 DUPLICATE 的貼文（預設 30）",
    )
    parser.add_argument("--chunk", type=int, default=2000, help="每塊處理筆數（即寫，可續跑）")
    parser.add_argument("--batch-size", type=int, default=64, help="模型推論 batch size")
    args = parser.parse_args()
    asyncio.run(main(args.min_quality, args.chunk, args.batch_size))
