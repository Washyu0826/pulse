"""
事件摘要端到端管線執行器（Faithful Event Summarizer 的 KEYSTONE runner）。

把一批**來源貼文**（Threads AI 貼文）丟進 `ml.event_pipeline.run_pipeline`，一條龍跑：

    向量化 → 門檻分群成「事件」→ MMR 抽關鍵句 → 帶 [n] 引註的繁中摘要 → NLI 忠實度查核

每個事件輸出一行 JSON，採**全管線共用的標準輸出 schema**（與電子報「今日事件」區塊、
前端 `EventSummary`、以及 `scripts/evaluate_summaries.py` 三者共享，欄位見下）。

────────────────────────────────────────────────────────────────────────
輸入 schema（PRIMARY：貼文 JSONL，每行一個貼文物件）
────────────────────────────────────────────────────────────────────────
    {
      "post_id": "th_1001",     # 或 "id"；缺則用行號（0-based 索引）
      "text": "貼文內文…",       # 或 "content" / "body"
      "theme": "新工具",          # 可選（會被帶進輸出的 theme，取事件代表貼文的 theme）
      "created_at": "…",         # 可選，目前不參與運算
      "url": "https://…",        # 可選，會被帶進引註
      "source": "Threads@xxx"    # 可選，會被帶進引註（來源標籤）
    }

我們**只接受貼文形狀**（而非 events.sample.jsonl 那種 event_id/key_sentences 的事件形狀）：
本 runner 的職責就是「**自己分群**」——把散落貼文聚成事件，這正是 `run_pipeline` 的核心。
事件形狀的檔案（已預先抽好 key_sentences、跳過分群）請改用 `scripts/summarize_events.py`。
demo 用 `docs/samples/posts.sample.jsonl`（11 篇台灣 AI Threads 貼文，含 3 個清楚事件叢集
＋ 1 篇雜訊單貼，min_size>=2 時雜訊自然被剔除）。

────────────────────────────────────────────────────────────────────────
輸出 schema（CANONICAL，每行一個事件）
────────────────────────────────────────────────────────────────────────
    {
      "event_id": "evt_001",            # 依事件順序給 evt_001、evt_002…（確定性）
      "title": "…",                     # 取自事件代表貼文（最靠形心者）開頭文字
      "summary": "…帶 [n] 引註的繁中摘要…",
      "citations": [                     # summary 實際引用到的來源（依編號排序）
        {"n": 1, "url": "https://…", "source": "Threads@xxx", "post_id": "th_1001"}
      ],
      "member_count": 4,                # 該事件叢集的成員貼文數
      "theme": "新工具",                  # 代表貼文的 theme（可為 null）
      "faithfulness_score": 0.83,        # FaithfulnessReport.faithfulness_score
      "issues": {"ok": true, "empty": false,
                 "uncited_sentences": [], "out_of_range_ids": []}  # SummaryIssues.to_json()
    }

引註 [n] ↔ 來源對齊：依 event_pipeline 的契約，summary 的 `[n]` 對齊「第 n 條關鍵句」
（`result.key_sentences[n-1]`），我們再用該關鍵句的 post_id 回查原貼文取 url / source。

────────────────────────────────────────────────────────────────────────
兩種模型模式
────────────────────────────────────────────────────────────────────────
- 預設（real）：延遲建 BGE-M3 embedder + 本機 Ollama Qwen generate_fn + mDeBERTa NLI。
  三者皆**惰性建立**，只有真的要跑 real 模式時才 import 重依賴；缺套件 / Ollama 未開會給
  清楚錯誤。逐事件 try/except，單一事件失敗不會中斷整批。
- `--fake`：用確定性的假 callable（token-bag embedder + 逐來源引註 generate + 子集蘊含
  NLI），**完全不需重依賴、不打 Ollama**。這是作品集 demo 與 sample 產生器走的路徑。

用法（系統 Python；--fake 不需任何重依賴）：
    # 產生 demo 輸出（離線、確定性）
    python scripts/run_event_pipeline.py docs/samples/posts.sample.jsonl --fake \
        --out docs/samples/pipeline_output.sample.jsonl
    # 真實模式（需 FlagEmbedding + Ollama + transformers，且 Ollama 服務開著）
    python scripts/run_event_pipeline.py posts.jsonl --out events.jsonl --model qwen2.5:7b
"""
import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "ml"))

# 只 import 純編排模組（event_pipeline 自身不帶重依賴）；重模型工廠在 real 模式才 lazy 取用。
from ml import event_pipeline  # noqa: E402


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------
def _load_posts(path: Path) -> list[dict]:
    """讀貼文 JSONL（略過空行）。每行需為含 text/content/body 的物件。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到貼文檔：{path}")
    posts: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {i} 行不是合法 JSON：{e}") from e
        if not isinstance(obj, dict):
            raise ValueError(f"第 {i} 行不是 JSON 物件。")
        if "key_sentences" in obj and not any(k in obj for k in ("text", "content", "body")):
            raise ValueError(
                f"第 {i} 行看起來是『事件形狀』（含 key_sentences、無貼文內文）。"
                "本 runner 只吃『貼文形狀』並自行分群；事件形狀請改用 "
                "scripts/summarize_events.py。"
            )
        posts.append(obj)
    return posts


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# 輸出組裝：把 EventSummaryResult → 標準輸出 schema
# ---------------------------------------------------------------------------
def _post_text(post: dict) -> str:
    for key in ("text", "content", "body"):
        v = post.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _make_title(text: str, *, max_chars: int = 24) -> str:
    """取代表貼文開頭文字當標題：到第一個句末標點為止，或截斷到 max_chars。"""
    text = (text or "").strip().replace("\n", " ")
    if not text:
        return "（無標題）"
    m = re.search(r"[。！？!?]", text)
    head = text[: m.start()] if m else text
    head = head.strip()
    if len(head) > max_chars:
        head = head[:max_chars] + "…"
    return head or "（無標題）"


def result_to_record(
    result: event_pipeline.EventSummaryResult,
    posts: list[dict],
    *,
    event_id: str,
) -> dict:
    """
    把單一 `EventSummaryResult` 轉成標準輸出 schema（純函式、確定性）。

    citations：取 summary 實際出現過的引註編號（cited_ids），每個 n 對齊第 n 條關鍵句
    （key_sentences[n-1]），再回查原貼文取 url / source / post_id。
    越界編號（不在 1..len(key_sentences)）跳過——validate_summary 已記進 issues。

    ⚠️ 索引轉換：`extract_key_sentences` 是對「事件成員貼文」（member_posts，即
    `[posts[i] for i in cluster.members]`）抽句，故 `KeySentence.post_index` 是**成員清單內
    的局部索引**，須經 `cluster.members[local_idx]` 轉回全域 posts 索引才取得正確來源貼文。
    """
    cluster = result.cluster
    rep_post = posts[cluster.representative]
    summary = result.summary
    report = result.faithfulness

    key_sentences = result.key_sentences
    citations: list[dict] = []
    cited_ids = sorted(summary.cited_ids) if summary is not None else []
    for n in cited_ids:
        if not (1 <= n <= len(key_sentences)):
            continue  # 越界引註：issues 會記，這裡不放進 citations
        ks = key_sentences[n - 1]
        # post_index 為「成員清單內」局部索引 → 轉回全域 posts 索引取原貼文。
        if 0 <= ks.post_index < len(cluster.members):
            global_idx = cluster.members[ks.post_index]
            src_post = posts[global_idx]
        else:
            src_post = {}
        citations.append(
            {
                "n": n,
                "url": src_post.get("url"),
                "source": src_post.get("source"),
                "post_id": src_post.get("post_id", src_post.get("id")),
            }
        )

    return {
        "event_id": event_id,
        "title": _make_title(_post_text(rep_post)),
        "summary": summary.text if summary is not None else "",
        "citations": citations,
        "member_count": cluster.size,
        "theme": rep_post.get("theme"),
        "faithfulness_score": round(report.faithfulness_score, 4) if report is not None else 0.0,
        "issues": result.issues.to_json() if result.issues is not None else {},
    }


# ---------------------------------------------------------------------------
# FAKE 模型（確定性、零重依賴）—— 作品集 demo 與 sample 產生器專用
# ---------------------------------------------------------------------------
_FAKE_DIM = 64
_TOKEN_RE = re.compile(r"[a-z0-9]+|[一-鿿]")


def _fake_tokens(text: str) -> list[str]:
    """token-bag 切詞：ASCII 英數連續成詞、中文逐字。與 test_event_pipeline.py 同套路。"""
    return _TOKEN_RE.findall((text or "").lower())


def fake_embed(text: str) -> list[float]:
    """token-bag hash embedder → 固定維度 → L2 正規化。同字句同向量、共享 token 餘弦高。"""
    vec = [0.0] * _FAKE_DIM
    for tok in _fake_tokens(text):
        h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
        vec[h % _FAKE_DIM] += 1.0
    n = math.sqrt(sum(x * x for x in vec))
    if n == 0.0:
        return vec
    return [x / n for x in vec]


_SRC_LINE_RE = re.compile(r"^\[(\d+)\]\s*(.*?)(?:（來源：.*）)?\s*$")


def _parse_prompt_sources(prompt: str) -> list[tuple[int, str]]:
    """從 summarize.build_summary_prompt 的 prompt 抽出 (編號, 來源文字) 清單。"""
    out: list[tuple[int, str]] = []
    in_block = False
    for line in prompt.splitlines():
        s = line.strip()
        if s == "來源：":
            in_block = True
            continue
        if not in_block:
            continue
        if s == "事件摘要：":
            break
        m = _SRC_LINE_RE.match(s)
        if m:
            out.append((int(m.group(1)), m.group(2).strip()))
    return out


def make_fake_generate(head_chars: int = 18):
    """
    工廠：回傳一個確定性 fake generate_fn。

    對 prompt 裡每條編號來源句，取其前 head_chars 字並逐句附上對應 [n] 引註，串成一段
    「忠實」摘要（只用來源句的字、引註正確）。head_chars 不同 → 摘要措辭略異，方便產
    「系統 A / 系統 B」兩個略有差異的版本做 bake-off。
    """

    def generate_fn(prompt: str) -> str:
        srcs = _parse_prompt_sources(prompt)
        parts = []
        for n, text in srcs:
            head = text[:head_chars] if text else text
            head = head.rstrip("，,。.、")
            if head:
                parts.append(f"{head} [{n}]。")
        return "".join(parts)

    return generate_fn


def fake_nli(premise: str, hypothesis: str) -> dict:
    """子集蘊含 fake：hypothesis 的 token ⊆ premise → 高蘊含；有交集 → 中性；否則低。"""
    p = set(_fake_tokens(premise))
    h = set(_fake_tokens(hypothesis))
    if h and h <= p:
        return {"entailment": 0.9, "neutral": 0.08, "contradiction": 0.02}
    if h & p:
        return {"entailment": 0.4, "neutral": 0.5, "contradiction": 0.1}
    return {"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05}


# ---------------------------------------------------------------------------
# 模型組裝
# ---------------------------------------------------------------------------
def build_ollama_embedder(model: str = "nomic-embed-text", host: str | None = None):
    """
    用本機 Ollama 的嵌入模型建 embed_fn（str → list[float]），完全地端、免裝 FlagEmbedding。

    BGE-M3 的繁中品質更好但要 pip install FlagEmbedding（且下載 ~2GB）；當本機已有 Ollama
    嵌入模型（如 nomic-embed-text）時，這條路零安裝、即跑。打 Ollama /api/embeddings 端點。
    """
    import httpx

    base = (host or "http://localhost:11434").rstrip("/")
    client = httpx.Client(timeout=120.0)

    def embed_fn(text: str) -> list[float]:
        r = client.post(
            f"{base}/api/embeddings",
            json={"model": model, "prompt": (text or " ")[:4000]},
        )
        r.raise_for_status()
        return r.json()["embedding"]

    return embed_fn


def build_real_models(model: str, host: str | None, *, embedder: str, embed_model: str):
    """
    延遲建三個真實模型 callable。只有 real 模式會走到，缺重依賴 / Ollama 時給清楚錯誤。

    回傳 (embed_fn, generate_fn, nli_fn)。任何 ImportError 都往上拋，由 main 統一報錯。
    embedder='bge' 走 BGE-M3（需 FlagEmbedding）；'ollama' 走本機 Ollama 嵌入模型（零安裝）。
    """
    from ml.faithfulness import build_nli_fn
    from ml.summarize import build_ollama_generate_fn

    if embedder == "ollama":
        embed_fn = build_ollama_embedder(model=embed_model, host=host)
    else:
        from ml.event_cluster import build_bge_m3_embedder

        embed_fn = build_bge_m3_embedder()
    host_kw = {"host": host} if host else {}
    generate_fn = build_ollama_generate_fn(model=model, **host_kw)
    nli_fn = build_nli_fn()
    return embed_fn, generate_fn, nli_fn


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(
        description="事件摘要端到端管線：貼文 JSONL → 分群 → 抽句 → 帶引註摘要 → 忠實度查核"
    )
    ap.add_argument("posts", type=Path, help="貼文 JSONL 路徑（每行一貼文，含 text/content）")
    ap.add_argument("--out", type=Path, default=None, help="結果 JSONL 路徑（預設 <posts>.events.jsonl）")
    ap.add_argument("--fake", action="store_true", help="用確定性假模型（離線 demo，不需重依賴 / Ollama）")
    ap.add_argument("--model", default="qwen2.5:7b", help="Ollama 模型名（real 模式，預設 qwen2.5:7b）")
    ap.add_argument("--host", default=None, help="Ollama host（real 模式；預設讀 OLLAMA_HOST）")
    ap.add_argument(
        "--embedder", choices=["bge", "ollama"], default="bge",
        help="real 模式嵌入器：bge=BGE-M3（需 FlagEmbedding）/ ollama=本機 Ollama 嵌入模型（零安裝）",
    )
    ap.add_argument("--embed-model", default="nomic-embed-text", help="--embedder ollama 時的 Ollama 嵌入模型名")
    ap.add_argument("--fake-head-chars", type=int, default=18, help="fake generate 取來源前幾字（調此產生系統 B）")
    # 管線旋鈕
    ap.add_argument("--threshold", type=float, default=0.6, help="分群餘弦門檻（>= 視為相連）")
    ap.add_argument("--min-size", type=int, default=2, help="最小事件群大小（小於此視為雜訊剔除）")
    ap.add_argument("--k", type=int, default=8, help="每事件抽的關鍵句數上限（MMR top-k）")
    ap.add_argument("--lambda-", type=float, default=0.7, dest="lambda_", help="MMR 相關/多樣 取捨（0~1）")
    ap.add_argument("--max-sentences", type=int, default=8, help="摘要句數上限")
    ap.add_argument("--lang", default="zh-Hant", help="摘要語言（預設繁中）")
    ap.add_argument("--entail-threshold", type=float, default=0.5, help="蘊含判定門檻")
    ap.add_argument("--contradict-threshold", type=float, default=0.5, help="矛盾判定門檻")
    args = ap.parse_args()

    try:
        posts = _load_posts(args.posts)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    if not posts:
        print("⚠️  貼文檔沒有任何貼文。", file=sys.stderr)
        return 1

    _emb = "BGE-M3" if args.embedder == "bge" else f"Ollama:{args.embed_model}"
    mode = "fake（離線確定性）" if args.fake else f"real（{_emb} + Ollama {args.model} + mDeBERTa）"
    print(f"📂 讀到 {len(posts)} 篇貼文：{args.posts}（模式：{mode}）")

    if args.fake:
        embed_fn = fake_embed
        generate_fn = make_fake_generate(args.fake_head_chars)
        nli_fn = fake_nli
    else:
        try:
            embed_fn, generate_fn, nli_fn = build_real_models(
                args.model, args.host, embedder=args.embedder, embed_model=args.embed_model
            )
        except ImportError as e:
            print(f"❌ 無法建立真實模型（缺依賴或 Ollama 未開）：{e}", file=sys.stderr)
            print("   提示：作品集 demo 請加 --fake（無需重依賴 / Ollama）。", file=sys.stderr)
            return 1

    # 先分群，再逐事件 try/except 跑摘要 → 單一事件失敗不中斷整批。
    from ml.event_cluster import cluster_events

    clusters = cluster_events(posts, embed_fn, threshold=args.threshold, min_size=args.min_size)
    print(f"🔗 分出 {len(clusters)} 個事件叢集（門檻 {args.threshold}、min_size {args.min_size}）")

    records: list[dict] = []
    failed = flagged = 0
    for idx, cluster in enumerate(clusters, 1):
        event_id = f"evt_{idx:03d}"
        try:
            result = event_pipeline.summarize_one_event(
                cluster,
                posts,
                embed_fn,
                generate_fn,
                nli_fn,
                k=args.k,
                lambda_=args.lambda_,
                max_sentences=args.max_sentences,
                lang=args.lang,
                entail_threshold=args.entail_threshold,
                contradict_threshold=args.contradict_threshold,
            )
        except Exception as e:  # noqa: BLE001 — 單一事件失敗不中斷整批
            failed += 1
            print(f"   ⚠️  事件 {event_id} 失敗，略過：{e}", file=sys.stderr)
            continue
        rec = result_to_record(result, posts, event_id=event_id)
        records.append(rec)
        if not rec["issues"].get("ok", True):
            flagged += 1

    out = args.out or args.posts.with_suffix(".events.jsonl")
    _write_jsonl(out, records)

    if records:
        avg = sum(r["faithfulness_score"] for r in records) / len(records)
        print(
            f"💾 完成：寫出 {len(records)} 個事件（驗證有問題 {flagged}、失敗 {failed}）"
            f"｜平均 faithfulness_score={avg:.4f} → {out}"
        )
    else:
        print(f"💾 完成：沒有產生任何事件（失敗 {failed}）→ {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
