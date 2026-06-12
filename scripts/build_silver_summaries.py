"""
產 silver 摘要訓練資料 —— 用地端 Qwen（Ollama）教師蒸餾，餵 scripts/train_summarizer.py（B 線 Step 2）。

從 DB 撈中文 AI 貼文 → 向量化分群成「事件」→ MMR 抽關鍵句 → Qwen 生成帶 [n] 引註的繁中摘要
→ 形式檢查 + NLI 忠實度過濾（教師也會幻覺，低分樣本不進訓練集）→ 寫 train_summarizer 對齊的
JSONL。純函式邏輯都在 `ml.silver_summaries`（有單元測試）；本腳本只做 IO / 編排。

輸出（預設 data/silver/summaries.jsonl，每行一事件，train_summarizer 直接可吃）：
    {"key_sentences": [{"text": "...", "source_id": 1, "source": ""}, ...],
     "summary": "OpenAI 發表 GPT-5 [1]。價格與前代相同 [2]。",
     "faithfulness_score": 0.83, "max_sentences": 8, "lang": "zh-Hant",
     "event_key": "…", "post_ids": [...], "model": "qwen2.5:7b", "created_at": "…"}
被過濾的樣本寫到 <out 同名>.rejected.jsonl（含 status / 摘要文字，供人工複查與續跑去重）。

增量續跑：事件以 `event_key`（成員貼文 id 的確定性雜湊）去重，已寫過（成功或被拒）的事件
重跑會自動跳過；要重試被拒事件加 --retry-rejected。

前置（非 dry-run）：Ollama 服務開著、已 pull 生成模型（預設 qwen2.5:7b，可用環境變數
PULSE_SUMMARIZE_MODEL 覆寫）與嵌入模型（預設 nomic-embed-text）；NLI 過濾需 transformers
（mDeBERTa，預設跑 CPU 以免跟 GPU 上的訓練/生成搶顯存）。

用法（系統 Python）：
    # 先 dry-run：只查 DB + 離線假向量分群，印出會處理的事件數與 prompt 範例（不打 Ollama）
    python scripts/build_silver_summaries.py --dry-run --days 90 --max-posts 1000
    # 實際生成（增量續跑；--limit 控制本次最多處理幾個事件）
    python scripts/build_silver_summaries.py --days 90 --max-posts 4000 --limit 200
    # 之後訓練
    python scripts/train_summarizer.py --silver data/silver/summaries.jsonl --out models/summarizer-lora
"""
import argparse
import asyncio
import hashlib
import math
import os
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
from ml import silver_summaries as ss  # noqa: E402
from ml.annotation import append_jsonl, load_jsonl  # noqa: E402
from ml.event_cluster import cluster_events, extract_key_sentences  # noqa: E402
from ml.event_pipeline import to_summary_key_sentences  # noqa: E402
from ml.summarize import build_summary_prompt  # noqa: E402
from sqlalchemy import select  # noqa: E402

_DEFAULT_MODEL = os.environ.get("PULSE_SUMMARIZE_MODEL", "qwen2.5:7b")
_CJK_RE = re.compile(r"[一-鿿]")


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


# ---------------------------------------------------------------------------
# DB：撈候選貼文（只 SELECT，不寫）
# ---------------------------------------------------------------------------
async def _fetch_posts(days: int, min_quality: int, max_posts: int) -> list[dict]:
    """撈近 N 天、過 DQC 品質門檻、非重複的貼文（與 distill_labels.py 同口徑）。"""
    async with AsyncSessionLocal() as session:
        rows = (
            await session.execute(
                select(Post.id, Post.source, Post.title, Post.content)
                .where((Post.quality_score.is_(None)) | (Post.quality_score >= min_quality))
                .where(~Post.quality_flags.contains(["DUPLICATE"]))
                .where(Post.posted_at >= datetime.now(UTC) - timedelta(days=days))
                .order_by(Post.posted_at.desc())
                .limit(max_posts)
            )
        ).all()
    posts: list[dict] = []
    for r in rows:
        text = f"{r.title or ''}。{r.content or ''}".strip("。 ").strip()
        if len(text) < 10:
            continue
        posts.append({"post_id": r.id, "source": r.source, "text": text})
    return posts


# ---------------------------------------------------------------------------
# 嵌入器：dry-run 用離線假向量（不打 Ollama）；real 用 Ollama 嵌入模型
# ---------------------------------------------------------------------------
_FAKE_DIM = 1024  # 維度夠大才不會 hash 碰撞讓所有貼文黏成一大群（single-link 會鏈式合併）
_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _fake_embed(text: str) -> list[float]:
    """token-bag hash embedder（與 run_event_pipeline.py --fake 同套路）：確定性、零依賴。
    只給 dry-run 估事件數與抽 prompt 範例用——分群品質與真嵌入不同，數字僅供參考。"""
    vec = [0.0] * _FAKE_DIM
    for tok in _TOKEN_RE.findall((text or "").lower()):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % _FAKE_DIM] += 1.0
    n = math.sqrt(sum(x * x for x in vec))
    return vec if n == 0.0 else [x / n for x in vec]


def _build_ollama_embed_fn(model: str, host: str | None):
    """Ollama 嵌入 embed_fn（str → list[float]；與 run_event_pipeline.py 同做法，零安裝）。"""
    import httpx

    base = (host or os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")).rstrip("/")
    client = httpx.Client(timeout=120.0)

    def embed_fn(text: str) -> list[float]:
        r = client.post(
            f"{base}/api/embeddings",
            json={"model": model, "prompt": (text or " ")[:4000]},
        )
        r.raise_for_status()
        return r.json()["embedding"]

    return embed_fn


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def _pending_clusters(clusters, posts: list[dict], done: set[str]) -> list[tuple[str, list, list]]:
    """過濾掉已處理事件：回傳 [(event_key, member_posts, post_ids), ...]。"""
    pending = []
    for cluster in clusters:
        member_posts = [posts[i] for i in cluster.members]
        post_ids = [p["post_id"] for p in member_posts]
        ekey = ss.event_key(post_ids)
        if ekey in done:
            continue
        pending.append((ekey, member_posts, post_ids))
    return pending


def main() -> int:
    ap = argparse.ArgumentParser(
        description="教師蒸餾產 silver 摘要訓練資料（DB 貼文 → 分群 → Qwen 摘要 → 忠實度過濾 → JSONL）"
    )
    ap.add_argument("--out", type=Path, default=_ROOT / "data" / "silver" / "summaries.jsonl",
                    help="輸出 JSONL（train_summarizer --silver 直接吃；預設 data/silver/summaries.jsonl）")
    # 取料
    ap.add_argument("--days", type=int, default=90, help="只撈最近 N 天的貼文")
    ap.add_argument("--min-quality", type=int, default=30, help="DQC 品質分門檻（NULL 也納入）")
    ap.add_argument("--max-posts", type=int, default=4000, help="最多撈幾篇貼文進分群")
    ap.add_argument("--zh", action=argparse.BooleanOptionalAction, default=True,
                    help="只取中文為主的貼文（CJK 比 >= 20%%；--no-zh 關閉）")
    # 分群 / 抽句
    ap.add_argument("--threshold", type=float, default=0.6, help="分群餘弦門檻（>= 視為相連）")
    ap.add_argument("--min-size", type=int, default=2, help="最小事件群大小（小於此視為雜訊剔除）")
    ap.add_argument("--k", type=int, default=8, help="每事件抽的關鍵句數上限（MMR top-k）")
    # 教師生成
    ap.add_argument("--model", default=_DEFAULT_MODEL,
                    help=f"Ollama 生成模型（預設 {_DEFAULT_MODEL}，環境變數 PULSE_SUMMARIZE_MODEL 可覆寫）")
    ap.add_argument("--host", default=None, help="Ollama host（預設讀 OLLAMA_HOST 或 127.0.0.1:11434）")
    ap.add_argument("--embed-model", default="nomic-embed-text", help="Ollama 嵌入模型名")
    ap.add_argument("--max-sentences", type=int, default=8, help="摘要句數上限（會寫進訓練記錄）")
    ap.add_argument("--lang", default="zh-Hant")
    # 過濾
    ap.add_argument("--min-faithfulness", type=float, default=0.5,
                    help="NLI 綜合忠實度門檻，低於即拒絕（train_summarizer 還可再用 --min-faithfulness 加嚴）")
    ap.add_argument("--nli", action=argparse.BooleanOptionalAction, default=True,
                    help="跑 mDeBERTa NLI 忠實度過濾（--no-nli 跳過：記錄不寫 faithfulness_score，品質較弱）")
    ap.add_argument("--nli-device", default="cpu",
                    help="NLI 推論裝置（預設 cpu，避免跟 GPU 上的訓練/Ollama 搶顯存；可填 cuda）")
    ap.add_argument("--require-ok", action=argparse.BooleanOptionalAction, default=True,
                    help="形式檢查不合格（無引註/越界引註）即拒絕（--no-require-ok 放行）")
    # 執行控制
    ap.add_argument("--limit", type=int, default=None, help="本次最多處理幾個事件（含被過濾者；預設不限）")
    ap.add_argument("--retry-rejected", action="store_true", help="重試先前被拒絕的事件（預設跳過）")
    ap.add_argument("--dry-run", action="store_true",
                    help="不打 Ollama：查 DB + 離線假向量分群，印出待處理事件數與 prompt 範例")
    args = ap.parse_args()

    rejected_path = args.out.with_name(args.out.stem + ".rejected.jsonl")

    # 增量續跑：已成功 + 已拒絕（除非 --retry-rejected）的 event_key 都跳過。
    done = ss.done_event_keys(load_jsonl(args.out))
    n_done_ok = len(done)
    n_done_rej = 0
    if not args.retry_rejected:
        rej_keys = ss.done_event_keys(load_jsonl(rejected_path))
        n_done_rej = len(rej_keys - done)
        done |= rej_keys
    print(f"📂 輸出：{args.out}（已生成 {n_done_ok} 筆、已拒絕 {n_done_rej} 筆會跳過）")

    posts = asyncio.run(_fetch_posts(args.days, args.min_quality, args.max_posts))
    if args.zh:
        posts = [p for p in posts if _cjk_ratio(p["text"]) >= 0.20]
    print(f"🗄️  DB 撈到 {len(posts)} 篇候選貼文（近 {args.days} 天、品質 >= {args.min_quality}"
          f"{'、中文為主' if args.zh else ''}）")
    if not posts:
        print("⚠️  沒有候選貼文。", file=sys.stderr)
        return 1

    # ----- dry-run：離線假向量分群（不打 Ollama），估事件數 + 印 prompt 範例 -----
    if args.dry_run:
        clusters = cluster_events(posts, _fake_embed, threshold=args.threshold, min_size=args.min_size)
        pending = _pending_clusters(clusters, posts, done)
        print(f"🔗 [dry-run] 假向量分群：{len(clusters)} 個事件叢集、待處理 {len(pending)} 個"
              f"（已處理 {len(clusters) - len(pending)} 個會跳過）")
        print("   ⚠️ dry-run 用離線 token-bag 假向量分群（不打 Ollama），事件數僅供參考；"
              "真跑時用 Ollama 嵌入，分群結果會不同。")
        n_todo = len(pending) if args.limit is None else min(args.limit, len(pending))
        print(f"   本次將處理 {n_todo} 個事件（--limit {args.limit}），"
              f"教師模型 {args.model}、NLI 過濾 {'開（' + args.nli_device + '）' if args.nli else '關'}、"
              f"忠實度門檻 {args.min_faithfulness}")
        if pending:
            ekey, member_posts, post_ids = pending[0]
            cluster_keys = extract_key_sentences(member_posts, _fake_embed, k=args.k)
            summary_keys = to_summary_key_sentences(cluster_keys)
            ids_preview = ", ".join(str(p) for p in post_ids[:10]) + ("…" if len(post_ids) > 10 else "")
            print(f"\n===== prompt 範例（事件 {ekey}，成員貼文 {len(post_ids)} 篇：{ids_preview}）=====")
            print(build_summary_prompt(summary_keys, max_sentences=args.max_sentences, lang=args.lang))
        print(f"\n✅ dry-run 完成：未呼叫 Ollama、未寫任何檔案。")
        return 0

    # ----- real：Ollama 嵌入 + 生成、（可選）NLI 過濾 -----
    try:
        embed_fn = _build_ollama_embed_fn(args.embed_model, args.host)
        from ml.summarize import build_ollama_generate_fn

        host_kw = {"host": args.host} if args.host else {}
        generate_fn = build_ollama_generate_fn(model=args.model, **host_kw)
    except ImportError as e:
        print(f"❌ 無法建立 Ollama 呼叫：{e}", file=sys.stderr)
        return 1

    nli_fn = None
    if args.nli:
        try:
            from ml.faithfulness import build_nli_fn

            nli_fn = build_nli_fn(device=args.nli_device)
        except ImportError as e:
            print(f"❌ NLI 需要 transformers：{e}（或加 --no-nli 跳過，但 silver 品質會變弱）",
                  file=sys.stderr)
            return 1
    else:
        print("⚠️  --no-nli：跳過忠實度過濾，記錄不會有 faithfulness_score（只剩形式檢查）。")

    print(f"🔗 用 Ollama 嵌入（{args.embed_model}）分群 {len(posts)} 篇貼文…")
    clusters = cluster_events(posts, embed_fn, threshold=args.threshold, min_size=args.min_size)
    pending = _pending_clusters(clusters, posts, done)
    if args.limit is not None:
        pending = pending[: args.limit]
    print(f"   {len(clusters)} 個事件叢集 → 本次處理 {len(pending)} 個（教師 {args.model}）")

    written = rejected = failed = 0
    for i, (ekey, member_posts, post_ids) in enumerate(pending, 1):
        try:
            cluster_keys = extract_key_sentences(member_posts, embed_fn, k=args.k)
            outcome = ss.distill_event(
                cluster_keys,
                generate_fn,
                nli_fn,
                max_sentences=args.max_sentences,
                lang=args.lang,
                min_faithfulness=args.min_faithfulness,
                require_ok=args.require_ok,
                extra={
                    "event_key": ekey,
                    "post_ids": post_ids,
                    "model": args.model,
                    "created_at": datetime.now(UTC).isoformat(),
                },
            )
        except Exception as e:  # noqa: BLE001 — 單一事件失敗不中斷整批（續跑會重試）
            failed += 1
            print(f"   ⚠️  事件 {ekey} 失敗，略過：{e}", file=sys.stderr)
            continue

        if outcome.ok:
            append_jsonl(args.out, outcome.record)
            written += 1
        else:
            rejected += 1
            append_jsonl(rejected_path, {
                "event_key": ekey,
                "post_ids": post_ids,
                "status": outcome.status,
                "faithfulness_score": outcome.faithfulness_score,
                "summary": outcome.summary_text,
                "issues": outcome.issues.to_json() if outcome.issues else None,
                "model": args.model,
                "created_at": datetime.now(UTC).isoformat(),
            })
        if i % 5 == 0:
            print(f"   …{i}/{len(pending)}（已寫 {written}、拒絕 {rejected}、失敗 {failed}）")

    print(f"💾 完成：新增 {written} 筆 silver（拒絕 {rejected} → {rejected_path.name}、失敗 {failed}）→ {args.out}")
    if written:
        print(f"   下一步：python scripts/train_summarizer.py --silver {args.out} --out models/summarizer-lora")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
