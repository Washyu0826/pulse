"""
每日「今日事件」產製器 —— DB 撈當日貼文 → 忠實事件摘要 pipeline → data/events_today.jsonl。

給 daily_refresh.ps1 在「寄電子報」之前跑：把當日散落的相關貼文聚成事件，產出帶行內
[n] 引註與忠實度分數的事件卡（電子報「🗂️ 今日事件」區與前端 /api/events/today 共用此檔）。

全地端模型（[[prefer-local-llm]]）：Ollama nomic 嵌入 + Ollama qwen 生成繁中摘要 +
mDeBERTa NLI 忠實度查核。模型 callable 由 scripts/run_event_pipeline.py 的工廠惰性建立。

設計取捨：
- 來源預設只取乾淨來源（hackernews / devto）。Threads 內文目前夾帶 UI chrome（使用者名/
  時間戳/回覆，見 content-quality agent backlog #1），會污染分群與摘要 → 清乾淨前先不納入。
  以 --sources 覆寫。
- 分群門檻預設 0.75：實測 nomic 嵌入下「所有 AI 貼文」彼此偏相似，0.55 會把多數貼文併成一團
  （摘要忠實度崩到 ~0.08）；0.75 為當前甜蜜點（連貫事件、忠實度 ~0.95）。未來換 BGE-M3 可再校。
- 貼文不足（<2 篇）或分不出事件時寫空檔、以 0 結束（不擋每日流程）。

用法（系統 Python，需 Ollama 開著 + transformers）：
    python scripts/build_today_events.py
    python scripts/build_today_events.py --hours 36 --threshold 0.75 --sources hackernews devto threads
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# TLS 攔截環境（本機 Avast）下，mDeBERTa 首次下載需走 Windows 信任庫（見 [[local-tls-smtp-gotchas]]）。
try:
    import truststore

    truststore.inject_into_ssl()
except Exception:  # noqa: BLE001 — 無 truststore 不致命（模型多半已快取）
    pass

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "api"))
sys.path.insert(0, str(_ROOT / "ml"))
sys.path.insert(0, str(_ROOT / "scripts"))

from ml import event_pipeline  # noqa: E402
from run_event_pipeline import _make_title, build_real_models, result_to_record  # noqa: E402


async def _fetch_posts(hours: int, min_quality: int, sources: list[str], limit: int) -> list[dict]:
    """撈近 N 小時、達品質門檻的貼文，組成 pipeline 要的 dict（含乾淨 title/title_zh 供標題用）。"""
    from api.database import AsyncSessionLocal
    from sqlalchemy import text

    placeholders = ",".join(f":s{i}" for i in range(len(sources)))
    params = {"h": hours, "q": min_quality, "lim": limit}
    params.update({f"s{i}": s for i, s in enumerate(sources)})
    async with AsyncSessionLocal() as s:
        rows = (
            await s.execute(
                text(
                    "select p.id, p.source, p.title, p.content, p.url, "
                    "th.label as theme, t.title_zh "
                    "from posts p "
                    "left join themes th on th.post_id=p.id "
                    "left join translations t on t.post_id=p.id "
                    "where p.posted_at >= now() - make_interval(hours => :h) "
                    "and (p.quality_score is null or p.quality_score >= :q) "
                    f"and p.source in ({placeholders}) "
                    "order by coalesce(p.score,0)+coalesce(p.num_comments,0) desc "
                    "limit :lim"
                ),
                params,
            )
        ).all()
    posts: list[dict] = []
    for r in rows:
        title = (r.title or "").strip()
        body = (r.content or "").strip()
        txt = title if not body else f"{title}. {body[:400]}"
        if len(txt.strip()) < 10:
            continue
        posts.append({
            "post_id": f"p{r.id}", "text": txt, "theme": r.theme, "url": r.url,
            "source": r.source, "title": title, "title_zh": r.title_zh,
        })
    return posts


def _clean_title(rep: dict, *, max_chars: int = 48) -> str:
    """事件標題：暫時優先英文原標題（乾淨、事實）。

    本來想用繁中標題 title_zh，但目前翻譯品質低（會把 'Claude Code' 音譯成 '克勞德代碼'、
    'D.C.' 變 'D 地'），用了反而更糟。待 content-quality 把翻譯修好（backlog #3）再切回
    title_zh。退英文標題 → 再退截斷內文開頭。"""
    t = (rep.get("title") or rep.get("title_zh") or "").strip().replace("\n", " ")
    if not t:
        t = _make_title(rep.get("text", ""))
    return t if len(t) <= max_chars else t[:max_chars] + "…"


def main() -> int:
    ap = argparse.ArgumentParser(description="每日今日事件產製（DB → 忠實事件摘要 JSONL）")
    ap.add_argument("--hours", type=int, default=36)
    ap.add_argument("--min-quality", type=int, default=30)
    ap.add_argument("--sources", nargs="+", default=["hackernews", "devto"])
    ap.add_argument("--limit", type=int, default=60, help="最多納入幾篇（依互動分數取前段）")
    ap.add_argument("--threshold", type=float, default=0.75, help="分群餘弦門檻")
    ap.add_argument("--min-size", type=int, default=2, help="最小事件群大小（小於視為雜訊）")
    ap.add_argument("--model", default="qwen2.5:7b")
    ap.add_argument("--embed-model", default="nomic-embed-text")
    ap.add_argument("--out", type=Path, default=_ROOT / "data" / "events_today.jsonl")
    args = ap.parse_args()

    posts = asyncio.run(_fetch_posts(args.hours, args.min_quality, args.sources, args.limit))
    print(f"📂 撈到 {len(posts)} 篇（來源 {', '.join(args.sources)}）")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    if len(posts) < args.min_size:
        args.out.write_text("", encoding="utf-8")
        print(f"⚠️  貼文不足，寫空事件檔 → {args.out}")
        return 0

    try:
        embed_fn, generate_fn, nli_fn = build_real_models(
            args.model, None, embedder="ollama", embed_model=args.embed_model
        )
    except ImportError as e:
        print(f"❌ 無法建立模型（缺依賴 / Ollama 未開）：{e}", file=sys.stderr)
        return 1

    results = event_pipeline.run_pipeline(
        posts, embed_fn, generate_fn, nli_fn, threshold=args.threshold, min_size=args.min_size
    )
    records: list[dict] = []
    for idx, result in enumerate(results, 1):
        rec = result_to_record(result, posts, event_id=f"evt_{idx:03d}")
        rec["title"] = _clean_title(posts[result.cluster.representative])
        records.append(rec)
    # 大事件（成員多）排前面，讓電子報「今日事件」頭條是當日最熱事件。
    records.sort(key=lambda r: r["member_count"], reverse=True)

    args.out.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8"
    )
    if records:
        avg = sum(r["faithfulness_score"] for r in records) / len(records)
        print(f"💾 寫出 {len(records)} 則事件（平均忠實度 {avg:.3f}）→ {args.out}")
    else:
        print(f"💾 沒有分出事件（貼文太分散）→ 空檔 {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
