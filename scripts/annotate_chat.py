"""
對話窗標註輔助 —— 配合 Claude Code 在對話中一次標 10 筆建 gold set。

與 scripts/annotate.py 同一套資料格式（ml.annotation.GoldLabel → data/gold/gold.jsonl），
兩者可互相續標。差別只在互動介面：annotate.py 是終端按鍵；這支把流程拆成兩個子命令，
由 Claude 在對話中代呈貼文、收使用者標籤後落檔。

用法：
    # 1) 建佇列：抽 N 篇中文為主貼文（分層、去已標、確定性 seed）→ data/gold/queue.jsonl
    python scripts/annotate_chat.py queue --target 300

    # 2) 寫入一批標註：讀含 labels 的 JSON 檔（見 _batch 範例）→ append 到 gold.jsonl
    python scripts/annotate_chat.py apply --batch data/gold/_batch.json

_batch.json 格式（post_id 必須在 queue.jsonl 內，快照原文取自佇列、非使用者輸入）：
    [{"post_id": 123, "sentiment": "neutral", "quality": "high", "theme": "新工具", "note": ""}]
"""
import argparse
import asyncio
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))

from ml.annotation import (  # noqa: E402
    QUALITY_LABELS,
    SENTIMENT_LABELS,
    THEME_LABELS,
    GoldLabel,
    append_jsonl,
    labeled_ids,
    load_jsonl,
    save_jsonl,
    stratified_sample,
)

GOLD = _ROOT / "data" / "gold" / "gold.jsonl"
QUEUE = _ROOT / "data" / "gold" / "queue.jsonl"
_CJK_RE = re.compile(r"[一-鿿]")
_TEXT_SNIPPET = 600  # 與 annotate.py 一致


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


async def build_queue(target: int, min_quality: int) -> None:
    """抽樣建佇列（鏡像 annotate.py：品質達標或未檢核、CJK≥20%、去已標、來源分層）。"""
    from api.database import AsyncSessionLocal
    from api.models.posts import Post
    from sqlalchemy import select

    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post.id, Post.source, Post.title, Post.content, Post.posted_at)
                .where((Post.quality_score.is_(None)) | (Post.quality_score >= min_quality))
                .order_by(Post.posted_at.desc())
            )
        ).all()

    done = labeled_ids(load_jsonl(GOLD), round=1)
    candidates = [
        {
            "id": r.id,
            "source": r.source,
            "title": r.title or "",
            "content": r.content or "",
            "posted_at": r.posted_at.isoformat() if r.posted_at else "",
        }
        for r in rows
        if r.id not in done and _cjk_ratio(f"{r.title or ''}{r.content or ''}") >= 0.20
    ]
    need = max(0, target - len(done))
    batch = stratified_sample(candidates, need, strata_key="source")
    save_jsonl(QUEUE, batch)
    by_src: dict[str, int] = {}
    for b in batch:
        by_src[b["source"]] = by_src.get(b["source"], 0) + 1
    print(f"🎯 已標 {len(done)}，目標 {target}，佇列抽出 {len(batch)} 筆 → {QUEUE}")
    print(f"   來源分佈：{json.dumps(by_src, ensure_ascii=False)}")


def apply_batch(batch_path: Path) -> None:
    """驗證並寫入一批標註；快照文字取自佇列（與 annotate.py 的 600 字截斷一致）。"""
    queue = {r["id"]: r for r in load_jsonl(QUEUE)}
    done = labeled_ids(load_jsonl(GOLD), round=1)
    items = json.loads(batch_path.read_text(encoding="utf-8"))

    written = skipped = 0
    for it in items:
        pid = it["post_id"]
        post = queue.get(pid)
        if post is None:
            print(f"  ⚠️ #{pid} 不在佇列，略過")
            skipped += 1
            continue
        if pid in done:
            print(f"  ⚠️ #{pid} 已標過（round=1），略過")
            skipped += 1
            continue
        sent, qual, theme = it["sentiment"], it["quality"], it["theme"]
        if sent not in SENTIMENT_LABELS or qual not in QUALITY_LABELS or theme not in THEME_LABELS:
            print(f"  ⚠️ #{pid} 標籤非法（{sent}/{qual}/{theme}），略過")
            skipped += 1
            continue
        rec = GoldLabel(
            post_id=pid,
            source=post["source"],
            sentiment=sent,
            quality=qual,
            text=f"{post['title']}. {post['content']}"[:_TEXT_SNIPPET],
            annotated_at=datetime.now(UTC).isoformat(),
            round=1,
            theme=theme,
            note=it.get("note", ""),
        )
        append_jsonl(GOLD, rec.to_json())
        done.add(pid)
        written += 1

    total = len(labeled_ids(load_jsonl(GOLD), round=1))
    print(f"💾 寫入 {written} 筆、略過 {skipped} 筆；gold 累計 {total} 筆。")


def main() -> None:
    ap = argparse.ArgumentParser(description="對話窗標註輔助（gold set）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queue", help="抽樣建佇列")
    q.add_argument("--target", type=int, default=300)
    q.add_argument("--min-quality", type=int, default=0)
    a = sub.add_parser("apply", help="寫入一批標註")
    a.add_argument("--batch", type=Path, required=True)
    args = ap.parse_args()

    if args.cmd == "queue":
        asyncio.run(build_queue(args.target, args.min_quality))
    else:
        apply_batch(args.batch)


if __name__ == "__main__":
    main()
