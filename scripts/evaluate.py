"""
Offline Evaluation 模型選型 bake-off（Phase 4）—— 一次比較「多種做法」，用統計挑最好的。

落地 ADR-008 + docs/research/offline-evaluation-literature.md。可同時評多個候選：
  - baseline（英文舊模型）：sentiment=twitter-roberta；theme=mDeBERTa zero-shot
  - 一個或多個微調中文模型目錄（--models，可多個，如不同 base/不同資料）
  - 選配 Qwen few-shot（--with-qwen）：地端 in-context 分類當對照

對每個候選算：macro-F1（per-class 平均）、accuracy、weighted-F1、per-class P/R/F1、confusion、
校準（ECE/Brier/NLL）、risk–coverage(AURC)+acc@coverage。依 macro-F1 排名，挑出 winner，
再把 winner 對每個其他候選做 McNemar（accuracy，Dietterich 1998）+ macro-F1 差 paired bootstrap CI
（Koehn 2004），多個對比用 BH-FDR 校正（Benjamini-Hochberg 1995）。落在重疊 CI 內不算贏。

這不是線上 A/B（無流量分流），是 Offline Evaluation —— 多模型在同一 gold set 的配對比較。

前置：系統 Python（GPU torch+transformers）、gold set、至少一個微調模型目錄（含 meta.json）。
用法：
    python scripts/evaluate.py --task sentiment --gold data/gold/gold.jsonl \
        --models models/sentiment-macbert models/sentiment-roberta-wwm --with-qwen --mlflow
"""
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
sys.path.insert(0, str(_ROOT / "ml"))

from ml.annotation import load_jsonl  # noqa: E402
from ml.metrics import (  # noqa: E402
    accuracy_at_coverage,
    benjamini_hochberg,
    brier_score,
    classification_metrics,
    expected_calibration_error,
    f1_macro_delta_ci,
    mcnemar,
    nll,
    risk_coverage_curve,
)

LABELS = {  # theme 對齊 ml.annotation.THEME_LABELS / theme.py
    "sentiment": ["negative", "neutral", "positive"],
    "theme": ["新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他"],
}
_GOLD_FIELD = {"sentiment": "sentiment", "theme": "theme"}
# Pred = (label, prob_dict|None)。prob_dict=None 代表無機率（如 Qwen 硬標）→ 不算校準。
Pred = tuple


def _load_gold(path: Path, task: str) -> list[tuple[str, str]]:
    field = _GOLD_FIELD[task]
    valid = set(LABELS[task])
    out = []
    for r in load_jsonl(path):
        if r.get("round", 1) != 1:
            continue
        label, text = r.get(field), r.get("text", "")
        if label in valid and text:
            out.append((text, label))
    return out


# ----------------------- 各候選的預測函式 -----------------------
def _predict_baseline(texts: list[str], task: str) -> list[Pred]:
    if task == "sentiment":
        from ml.sentiment import SentimentAnalyzer

        return [(r.label, dict(r.scores)) for r in SentimentAnalyzer().analyze_batch(texts)]
    from ml.theme import ThemeClassifier

    return [(r.label, dict(r.scores)) for r in ThemeClassifier().classify_batch(texts)]


def _predict_finetuned(texts: list[str], model_dir: Path, temperature: float) -> list[Pred]:
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device).eval()
    id2label = {i: model.config.id2label[i] for i in range(len(model.config.id2label))}
    out: list[Pred] = []
    for i in range(0, len(texts), 32):
        chunk = [(t or " ")[:2000] for t in texts[i : i + 32]]
        enc = tok(chunk, return_tensors="pt", truncation=True, max_length=256, padding=True).to(device)
        with torch.no_grad():
            logits = model(**enc).logits / max(temperature, 1e-3)  # 溫度校準
        for row in torch.softmax(logits, dim=-1).cpu().tolist():
            scores = {id2label[j]: float(row[j]) for j in range(len(row))}
            out.append((max(scores, key=scores.get), scores))
    return out


def _predict_qwen(texts: list[str], task: str) -> list[Pred]:
    from ml.distill import Distiller

    async def _run() -> list[Pred]:
        import httpx

        d = Distiller()
        res: list[Pred] = []
        async with httpx.AsyncClient(timeout=d.timeout) as client:
            for t in texts:
                lbl = await d.label(t, task, client=client)
                res.append((lbl or LABELS[task][0], None))  # 無機率
        return res

    return asyncio.run(_run())


# ----------------------- 評測材料 -----------------------
def _confidence(pred: str, probs: dict | None) -> float:
    if not probs:
        return 1.0
    return float(probs.get(pred, max(probs.values())))


def _calibration(preds: list[Pred], y_true: list[str], labels: list[str]) -> dict:
    if any(pr is None for _, pr in preds):
        return {"available": False}
    confidences = [_confidence(p, pr) for p, pr in preds]
    correct = [p == t for (p, _), t in zip(preds, y_true, strict=True)]
    probs = [pr for _, pr in preds]
    proper = all(0.9 <= sum(pr.get(lbl, 0.0) for lbl in labels) <= 1.1 for pr in probs)
    rc = risk_coverage_curve(confidences, correct)
    return {
        "available": True,
        "ece_15bin": expected_calibration_error(confidences, correct, n_bins=15),
        "ece_adaptive": expected_calibration_error(confidences, correct, n_bins=10, adaptive=True),
        "brier": brier_score(probs, y_true, labels) if proper else None,
        "nll": nll(probs, y_true) if proper else None,
        "aurc": rc["aurc"],
        "acc_at_coverage": {str(k): round(v, 4) for k, v in accuracy_at_coverage(confidences, correct).items()},
        "proper_probs": proper,
    }


def _build_candidates(args, texts, task) -> dict[str, list[Pred]]:
    """名稱 → 預測。順序：baseline、各微調模型、Qwen。"""
    cands: dict[str, list[Pred]] = {}
    if not args.no_baseline:
        name = "baseline-en" if task == "sentiment" else "baseline-zeroshot"
        print(f"   推論 {name}（舊模型）…")
        cands[name] = _predict_baseline(texts, task)
    for d in args.models or []:
        meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
        t = float(meta.get("temperature", 1.0))
        print(f"   推論 {d.name}（微調，T={t}）…")
        cands[d.name] = _predict_finetuned(texts, d, t)
    if args.with_qwen:
        print("   推論 qwen-fewshot（地端 in-context）…")
        cands["qwen-fewshot"] = _predict_qwen(texts, task)
    return cands


async def _persist_rows(rows: list[dict]) -> None:
    from api.database import AsyncSessionLocal
    from api.models.evaluation import EvaluationRun

    async with AsyncSessionLocal() as session:
        for row in rows:
            session.add(EvaluationRun(**row))
        await session.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="Offline Evaluation 模型選型 bake-off")
    ap.add_argument("--task", choices=["sentiment", "theme"], required=True)
    ap.add_argument("--gold", type=Path, required=True)
    ap.add_argument("--models", type=Path, nargs="*", default=[], help="微調模型目錄（可多個）")
    ap.add_argument("--no-baseline", action="store_true", help="不納入英文/zero-shot 舊模型")
    ap.add_argument("--with-qwen", action="store_true", help="納入 Qwen few-shot 候選")
    ap.add_argument("--eval-set", default="gold_zh_v1")
    ap.add_argument("--bootstrap", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--report", type=Path, default=None)
    ap.add_argument("--mlflow", action="store_true")
    ap.add_argument("--no-db", action="store_true")
    args = ap.parse_args()

    labels = LABELS[args.task]
    gold = _load_gold(args.gold, args.task)
    if len(gold) < 10:
        sys.exit(f"❌ gold 太少（{len(gold)} 筆）。先用 annotate.py 標。")
    texts = [t for t, _ in gold]
    y_true = [lbl for _, lbl in gold]
    print(f"🔬 task={args.task} · gold={len(gold)} 筆 · 候選評測中…")

    cands = _build_candidates(args, texts, task=args.task)
    if len(cands) < 2:
        sys.exit("❌ 至少要 2 個候選才能比較（給 --models 或保留 baseline）。")

    # 每個候選的指標 + 校準。
    metrics = {name: classification_metrics(y_true, [p for p, _ in preds], labels)
               for name, preds in cands.items()}
    calib = {name: _calibration(preds, y_true, labels) for name, preds in cands.items()}
    ranking = sorted(cands, key=lambda n: metrics[n]["f1_macro"], reverse=True)
    winner = ranking[0]

    # winner vs 每個其他候選：McNemar + macro-F1 差 CI；多重比較 BH-FDR。
    win_lab = [p for p, _ in cands[winner]]
    pairwise: dict[str, dict] = {}
    pvals: dict[str, float] = {}
    for name in ranking[1:]:
        other = [p for p, _ in cands[name]]
        mcn = mcnemar(y_true, win_lab, other)
        dl = f1_macro_delta_ci(y_true, win_lab, other, n_boot=args.bootstrap, seed=args.seed)
        pairwise[name] = {"mcnemar": mcn, "f1_delta": dl,
                          "ci_excludes_0": (dl["ci_low"] > 0 or dl["ci_high"] < 0)}
        pvals[name] = mcn["p_value"]
    bh = benjamini_hochberg(pvals, q=0.05)

    # ----------------------- 報告 -----------------------
    print("\n" + "=" * 70)
    print(f"  Bake-off 排名（依 macro-F1，n={len(gold)}）")
    print("-" * 70)
    print(f"  {'候選':24} {'macroF1':>8} {'acc':>6} {'wF1':>6} {'ECE':>6} {'AURC':>6}")
    for name in ranking:
        m, c = metrics[name], calib[name]
        ece = f"{c['ece_15bin']:.3f}" if c.get("available") else "  n/a"
        aurc = f"{c['aurc']:.3f}" if c.get("available") else "  n/a"
        flag = "🏆" if name == winner else "  "
        print(f"  {flag}{name:22} {m['f1_macro']:8.3f} {m['accuracy']:6.3f} "
              f"{m['f1_weighted']:6.3f} {ece:>6} {aurc:>6}")
    print("-" * 70)
    print(f"  winner = {winner}（與其他候選的配對顯著性，BH-FDR q=0.05）：")
    for name in ranking[1:]:
        pw, b = pairwise[name], bh[name]
        sig = "✓ 顯著優於" if (pw["ci_excludes_0"] and pw["f1_delta"]["f1_delta"] > 0 and b["reject"]) \
            else "· 未達顯著"
        print(f"    vs {name:22} ΔmacroF1={pw['f1_delta']['f1_delta']:+.3f} "
              f"CI[{pw['f1_delta']['ci_low']:+.3f},{pw['f1_delta']['ci_high']:+.3f}] "
              f"McNemar p_adj={b['p_adj']:.3f}  {sig}")
    only_marginal = all(not (pairwise[n]["ci_excludes_0"] and bh[n]["reject"]) for n in ranking[1:])
    print("-" * 70)
    if only_marginal:
        print(f"  ⚠️ winner（{winner}）對所有對手都未達統計顯著 → 選型需更多 gold 或視為平手。")
    else:
        print(f"  ✅ 建議採用：{winner}（至少顯著優於部分候選）。")
    print("=" * 70)

    report = {
        "task": args.task, "eval_set": args.eval_set, "sample_size": len(gold), "labels": labels,
        "ranking": ranking, "winner": winner,
        "metrics": metrics, "calibration": calib, "pairwise_vs_winner": pairwise, "bh_fdr": bh,
        "note": "silver-trained, gold-evaluated；落在重疊 CI 內不算贏（offline-evaluation-literature.md）",
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        print(f"📄 report → {args.report}")

    # 每個候選寫一列 evaluation_runs（winner 那列 baseline_model=第二名，附 McNemar）。
    if not args.no_db:
        runner_up = ranking[1] if len(ranking) > 1 else None
        rows = []
        for name in ranking:
            m = metrics[name]
            row = {
                "task": args.task, "model_version": name, "evaluation_set": args.eval_set,
                "sample_size": len(gold), "f1_macro": m["f1_macro"], "f1_weighted": m["f1_weighted"],
                "accuracy": m["accuracy"], "precision_per_class": m["precision_per_class"],
                "recall_per_class": m["recall_per_class"], "confusion_matrix": m["confusion_matrix"],
                "notes": f"bakeoff winner={winner}; rank={ranking.index(name) + 1}/{len(ranking)}",
            }
            if name == winner and runner_up:
                pw = pairwise[runner_up]
                row.update({
                    "baseline_model": runner_up, "mcnemar_statistic": pw["mcnemar"]["statistic"],
                    "mcnemar_p_value": pw["mcnemar"]["p_value"], "f1_delta": pw["f1_delta"]["f1_delta"],
                    "f1_delta_ci_low": pw["f1_delta"]["ci_low"], "f1_delta_ci_high": pw["f1_delta"]["ci_high"],
                })
            rows.append(row)
        try:
            asyncio.run(_persist_rows(rows))
            print(f"💾 已寫入 evaluation_runs（{len(rows)} 列）。")
        except Exception as e:  # noqa: BLE001
            print(f"⚠️ 寫 DB 失敗（用 --no-db 跳過）：{e}")

    if args.mlflow:
        import mlflow

        mlflow.set_experiment(f"pulse-bakeoff-{args.task}")
        for name in ranking:
            m, c = metrics[name], calib[name]
            with mlflow.start_run(run_name=name):
                mlflow.log_params({"task": args.task, "candidate": name, "is_winner": name == winner,
                                   "eval_set": args.eval_set, "n_gold": len(gold)})
                logm = {"f1_macro": m["f1_macro"], "accuracy": m["accuracy"], "f1_weighted": m["f1_weighted"]}
                if c.get("available"):
                    logm.update({"ece": c["ece_15bin"], "aurc": c["aurc"]})
                mlflow.log_metrics(logm)
        print("📈 已記錄到 MLflow（每個候選一個 run）。")


if __name__ == "__main__":
    main()
