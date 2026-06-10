"""
事件摘要產生器（Faithful Event Summarizer，Step 1：Qwen-only baseline）。

從 JSONL 讀事件（每行一個事件、含其關鍵句），用地端 Qwen2.5（Ollama）逐事件產帶引註的繁中摘要，
解析 + 驗證後寫出結果 JSONL。無 DB 依賴（不需 Docker 即可跑）。

輸入事件 JSONL 結構（每行一個 JSON 物件；未列欄位會忽略）：
    {
      "event_id": "evt_001",                 # 事件識別碼（字串或數字，可選，缺則用行號）
      "title": "GPT-5 發表",                  # 事件標題（可選，僅供結果回填）
      "key_sentences": [                      # 必填：該事件的來源關鍵句（依重要度排好）
        {"text": "OpenAI 發表 GPT-5...", "source_id": 101, "source": "Threads"},
        {"text": "API 價格不變...",       "source_id": 102}
      ]
    }
key_sentences 也接受純字串清單（["句一", "句二"]）或省略 source_id / source 的 dict。

輸出結果 JSONL（每行一個 JSON 物件）：
    {
      "event_id": ..., "title": ...,
      "summary": "...帶 [n] 引註的繁中摘要...",
      "sentences": [...], "cited_ids": [1, 2, 3],
      "n_sources": 3,
      "issues": {"ok": true, "empty": false, "uncited_sentences": [], "out_of_range_ids": []},
      "model": "qwen2.5:7b"
    }

前置（非 dry-run 時）：Ollama 服務開著且已 pull 模型（預設 qwen2.5:7b）。
用法（系統 Python；需 httpx + Ollama）：
    # 先看每個事件會送什麼 prompt（不呼叫模型）
    python scripts/summarize_events.py events.jsonl --dry-run
    # 實際產摘要
    python scripts/summarize_events.py events.jsonl --out summaries.jsonl --model qwen2.5:7b
"""
import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "ml"))

from ml.summarize import (  # noqa: E402
    build_ollama_generate_fn,
    build_summary_prompt,
    summarize_event,
)


def _load_events(path: Path) -> list[dict]:
    """讀事件 JSONL（略過空行；每行需為含 key_sentences 的物件）。"""
    if not path.exists():
        raise FileNotFoundError(f"找不到事件檔：{path}")
    events: list[dict] = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {i} 行不是合法 JSON：{e}") from e
        if not isinstance(obj, dict) or "key_sentences" not in obj:
            raise ValueError(f"第 {i} 行缺 key_sentences 欄位。")
        events.append(obj)
    return events


def _write_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description="地端 Qwen 事件忠實摘要（帶 [n] 引註）")
    ap.add_argument("events", type=Path, help="事件 JSONL 路徑（每行一事件，含 key_sentences）")
    ap.add_argument("--out", type=Path, default=None, help="結果 JSONL 路徑（預設 <events>.summaries.jsonl）")
    ap.add_argument("--model", default="qwen2.5:7b", help="Ollama 模型名（預設 qwen2.5:7b）")
    ap.add_argument("--host", default=None, help="Ollama host（預設讀 OLLAMA_HOST 或 127.0.0.1:11434）")
    ap.add_argument("--max-sentences", type=int, default=8, help="摘要句數上限")
    ap.add_argument("--dry-run", action="store_true", help="只印每個事件的 prompt，不呼叫模型")
    args = ap.parse_args()

    try:
        events = _load_events(args.events)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1
    if not events:
        print("⚠️  事件檔沒有任何事件。", file=sys.stderr)
        return 1

    print(f"📂 讀到 {len(events)} 個事件：{args.events}")

    if args.dry_run:
        for i, ev in enumerate(events, 1):
            eid = ev.get("event_id", i)
            print(f"\n===== 事件 {eid}（prompt 預覽）=====")
            print(build_summary_prompt(ev["key_sentences"], max_sentences=args.max_sentences))
        print(f"\n✅ dry-run 完成：印出 {len(events)} 個 prompt，未呼叫模型。")
        return 0

    # 非 dry-run 才 lazy 建 Ollama generate_fn（缺 httpx / 服務未開都在這裡給清楚錯誤）。
    out = args.out or args.events.with_suffix(".summaries.jsonl")
    host_kw = {"host": args.host} if args.host else {}
    try:
        generate_fn = build_ollama_generate_fn(model=args.model, **host_kw)
    except ImportError as e:
        print(f"❌ 無法建立 Ollama 呼叫：{e}", file=sys.stderr)
        return 1

    print(f"🤖 呼叫本地 Ollama（model={args.model}）→ 寫入 {out}")
    written = flagged = failed = 0
    for i, ev in enumerate(events, 1):
        eid = ev.get("event_id", i)
        try:
            summary, issues = summarize_event(
                ev["key_sentences"], generate_fn, max_sentences=args.max_sentences
            )
        except Exception as e:  # noqa: BLE001 — 單一事件失敗不中斷整批
            failed += 1
            print(f"   ⚠️  事件 {eid} 摘要失敗，略過：{e}", file=sys.stderr)
            continue
        record = {
            "event_id": eid,
            "title": ev.get("title", ""),
            "summary": summary.text,
            "sentences": summary.sentences,
            "cited_ids": sorted(summary.cited_ids),
            "n_sources": _n_sources(ev),
            "issues": issues.to_json(),
            "model": args.model,
        }
        _write_jsonl(out, record)
        written += 1
        if not issues.ok:
            flagged += 1
        if i % 20 == 0:
            print(f"   …{i}/{len(events)}（已寫 {written}、有問題 {flagged}、失敗 {failed}）")

    print(f"💾 完成：寫出 {written} 筆（驗證有問題 {flagged}、失敗 {failed}）→ {out}")
    return 0


def _n_sources(event: dict) -> int:
    """事件的來源關鍵句數（引註合法範圍上界）。"""
    ks = event.get("key_sentences") or []
    return len(ks)


if __name__ == "__main__":
    raise SystemExit(main())
