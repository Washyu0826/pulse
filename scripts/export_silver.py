"""
把 DB 既有標籤（zero-shot/RoBERTa silver）匯出成 train_classifier.py 吃的 JSONL（{text, label}）。

用途：在還沒有 gold / Qwen 蒸餾 silver 前，先用現有 silver 把訓練→校準→評測管線在 GPU 上跑通，
產出 baseline 模型 + 指標（誠實標註：這是「蒸餾現有 teacher」，驗證管線 ≠ 證明贏過 zero-shot；
正式要贏 zero-shot 需 Qwen 蒸餾或人工 gold）。只讀 DB（SELECT），不寫。

用法：
    ENVIRONMENT=production python scripts/export_silver.py --task theme --out data/silver/theme.jsonl
    ENVIRONMENT=production python scripts/export_silver.py --task sentiment --out data/silver/sentiment.jsonl --limit 20000
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))

from api.database import AsyncSessionLocal  # noqa: E402

_TABLE = {"theme": "themes", "sentiment": "sentiments"}


async def main(task: str, out: Path, limit: int | None, min_quality: int) -> None:
    from sqlalchemy import text

    tbl = _TABLE[task]
    # 取 (貼文文字, 標籤)：已過 DQC 品質門檻、且該任務已標。低品質/重複不納入訓練。
    sql = f"""
        SELECT p.title, p.content, t.label
        FROM posts p JOIN {tbl} t ON t.post_id = p.id
        WHERE p.quality_score >= :mq
          AND NOT (p.quality_flags @> ARRAY['DUPLICATE'])
          AND t.label IS NOT NULL AND t.label <> ''
    """
    if limit:
        sql += "\n        ORDER BY p.id LIMIT :lim"

    params: dict = {"mq": min_quality}
    if limit:
        params["lim"] = limit

    async with AsyncSessionLocal() as s:
        rows = (await s.execute(text(sql), params)).all()

    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    dist: dict[str, int] = {}
    with out.open("w", encoding="utf-8") as f:
        for title, content, label in rows:
            txt = f"{title or ''}. {content or ''}".strip()
            if len(txt) < 5:
                continue
            f.write(json.dumps({"text": txt[:2000], "label": label}, ensure_ascii=False) + "\n")
            dist[label] = dist.get(label, 0) + 1
            n += 1
    print(f"💾 匯出 {n} 筆 silver（task={task}）→ {out}")
    print("📊 標籤分布：", dict(sorted(dist.items(), key=lambda x: -x[1])))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", choices=["theme", "sentiment"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--min-quality", type=int, default=30)
    args = ap.parse_args()
    asyncio.run(main(args.task, args.out, args.limit, args.min_quality))
