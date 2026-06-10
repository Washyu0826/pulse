"""
摘要品質 Bake-off 編排器 —— 兩套摘要器在同一事件集上的忠實度配對比較（無模型、無 DB）。

讀兩個由摘要 / 評測管線產生的結果 JSONL（每套系統一個檔），用事件 id 做 inner join 對齊
（只比兩邊都有的事件），抽出每事件的忠實度分數，跑 ml.summary_eval.compare_systems，
印出並（可選）寫出 markdown 報告。純統計編排：不載入任何模型、不連 DB、不打雲端 API。

輸入 JSONL 結構（每行一個 JSON 物件；容忍 scripts/summarize_events.py 的輸出 schema）：
    - 事件識別：依序找 --id-field（預設 "event_id"），找不到退回 "id"。
      （summarize_events.py 寫的是 "event_id"。）
    - 忠實度分數：依序找 --score-field（預設 "faithfulness"），找不到再試
      "faithfulness_score"（對齊 faithfulness.py 的 FaithfulnessReport.faithfulness_score）。
      分數需可轉成 float；解析不出分數的行會被略過並計數。
    其餘欄位忽略。

注意：summarize_events.py 目前只寫 issues（驗證旗標），尚未把 faithfulness 分數寫進 JSONL。
本腳本期望的是「已含每事件忠實度分數」的結果檔（即跑過 faithfulness_report 後落地的檔）；
欄位名以 --score-field 調整即可，預設同時相容 "faithfulness" 與 "faithfulness_score"。

用法（系統 Python；只需 stdlib + ml 套件）：
    python scripts/evaluate_summaries.py qwen.jsonl lora.jsonl \
        --name-a qwen --name-b lora --out reports/summary_bakeoff.md
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

from ml.summary_eval import compare_systems, format_markdown_report  # noqa: E402

_ID_FALLBACKS = ("id",)
_SCORE_FALLBACKS = ("faithfulness_score",)


def _extract_id(rec: dict, id_field: str) -> object | None:
    """取事件 id：先 id_field、再退回常見別名。回傳原值（字串/數字皆可當 join key）。"""
    if id_field in rec and rec[id_field] is not None:
        return rec[id_field]
    for alt in _ID_FALLBACKS:
        if alt in rec and rec[alt] is not None:
            return rec[alt]
    return None


def _extract_score(rec: dict, score_field: str) -> float | None:
    """取忠實度分數：先 score_field、再退回別名。非數值回傳 None（上層計入「略過」）。"""
    for key in (score_field, *_SCORE_FALLBACKS):
        if key in rec and rec[key] is not None:
            try:
                return float(rec[key])
            except (TypeError, ValueError):
                return None
    return None


def _load_scores(path: Path, id_field: str, score_field: str) -> tuple[dict, int]:
    """
    讀結果 JSONL → {event_id: score}。回傳 (對照表, 略過行數)。

    略過：空行、無 id、或抽不出 float 分數的行。重複 id 以最後一筆為準（並印警告）。
    """
    if not path.exists():
        raise FileNotFoundError(f"找不到結果檔：{path}")
    by_id: dict = {}
    skipped = 0
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"{path} 第 {i} 行不是合法 JSON：{e}") from e
        if not isinstance(rec, dict):
            skipped += 1
            continue
        eid = _extract_id(rec, id_field)
        score = _extract_score(rec, score_field)
        if eid is None or score is None:
            skipped += 1
            continue
        key = str(eid)
        if key in by_id:
            print(f"⚠️  {path.name} 第 {i} 行事件 id 重複（{key}），以後者覆蓋。", file=sys.stderr)
        by_id[key] = score
    return by_id, skipped


def main() -> int:
    ap = argparse.ArgumentParser(
        description="摘要品質 bake-off：兩套摘要器在同一事件集的忠實度配對比較（純統計）"
    )
    ap.add_argument("file_a", type=Path, help="系統 A 的結果 JSONL（含事件 id 與忠實度分數）")
    ap.add_argument("file_b", type=Path, help="系統 B 的結果 JSONL")
    ap.add_argument("--name-a", default=None, help="系統 A 名稱（預設取檔名）")
    ap.add_argument("--name-b", default=None, help="系統 B 名稱（預設取檔名）")
    ap.add_argument("--id-field", default="event_id", help="事件 id 欄位名（預設 event_id）")
    ap.add_argument(
        "--score-field",
        default="faithfulness",
        help="忠實度分數欄位名（預設 faithfulness；自動相容 faithfulness_score）",
    )
    ap.add_argument("--margin", type=float, default=0.0, help="逐事件勝負門檻（差需 > margin 才算贏）")
    ap.add_argument("--bootstrap", type=int, default=2000, help="bootstrap 重抽次數")
    ap.add_argument("--seed", type=int, default=0, help="bootstrap 亂數種子（可重現）")
    ap.add_argument("--alpha", type=float, default=0.05, help="CI 顯著水準（0.05 → 95%% CI）")
    ap.add_argument("--out", type=Path, default=None, help="markdown 報告輸出路徑（可選）")
    args = ap.parse_args()

    name_a = args.name_a or args.file_a.stem
    name_b = args.name_b or args.file_b.stem

    try:
        scores_a, skip_a = _load_scores(args.file_a, args.id_field, args.score_field)
        scores_b, skip_b = _load_scores(args.file_b, args.id_field, args.score_field)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ {e}", file=sys.stderr)
        return 1

    if not scores_a:
        print(f"❌ {args.file_a} 沒有可用的（id, 分數）紀錄。", file=sys.stderr)
        return 1
    if not scores_b:
        print(f"❌ {args.file_b} 沒有可用的（id, 分數）紀錄。", file=sys.stderr)
        return 1

    # inner join：只比兩邊都有的事件，並以確定順序排列（join key 排序 → 可重現）。
    common = sorted(set(scores_a) & set(scores_b))
    if not common:
        print(
            f"❌ 兩檔沒有共同事件 id（{name_a}={len(scores_a)} 筆、{name_b}={len(scores_b)} 筆）。"
            f"檢查 --id-field 是否正確。",
            file=sys.stderr,
        )
        return 1

    paired_a = [scores_a[k] for k in common]
    paired_b = [scores_b[k] for k in common]

    print(f"📂 {name_a}：{len(scores_a)} 筆（略過 {skip_a}）；{name_b}：{len(scores_b)} 筆（略過 {skip_b}）")
    print(f"🔗 共同事件（配對）：{len(common)} 筆")

    comparison = compare_systems(
        name_a,
        paired_a,
        name_b,
        paired_b,
        n_boot=args.bootstrap,
        seed=args.seed,
        alpha=args.alpha,
        margin=args.margin,
    )

    sa = comparison["systems"][name_a]
    sb = comparison["systems"][name_b]
    dci = comparison["delta_ci"]
    wr = comparison["win_rate"]
    print("\n" + "=" * 64)
    print(f"  摘要品質 Bake-off（指標欄位：{args.score_field}）")
    print("-" * 64)
    print(f"  {name_a:20} mean={sa['mean']:.4f}  median={sa['median']:.4f}  n={sa['n']}")
    print(f"  {name_b:20} mean={sb['mean']:.4f}  median={sb['median']:.4f}  n={sb['n']}")
    print("-" * 64)
    print(f"  Δ = mean({name_a}) − mean({name_b}) = {dci['delta']:+.4f}")
    print(f"  配對 bootstrap {int((1 - args.alpha) * 100)}% CI = [{dci['ci_low']:+.4f}, {dci['ci_high']:+.4f}]")
    print(f"  逐事件勝率：{name_a} {wr['wins_a']} 勝 / {name_b} {wr['wins_b']} 勝 / 平手 {wr['ties']}")
    print("-" * 64)
    print(f"  決策：{comparison['decision']}")
    print("=" * 64)

    if args.out:
        md = format_markdown_report(comparison)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(md, encoding="utf-8")
        print(f"📄 markdown 報告 → {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
