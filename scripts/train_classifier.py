"""
微調中文分類器 —— hfl/chinese-macbert-base，取代英文情緒模型 / zero-shot 主題模型（Phase 3）。

依據：Bucher & Martini 2024（微調小模型 > zero-shot 生成模型）、MacBERT（Cui 2020，
最強小型中文編碼器，~100M，4060 全量微調可行）、Guo 2017（溫度校準）。

資料分工（對齊 annotation-guidelines.md §7）：
- **gold**（人工驗證）→ 當乾淨的驗證/評估集（held-out），不拿來訓練。
- **silver**（Qwen 蒸餾）→ 訓練集。若無 silver 則退而用 gold 切分訓練。
訓練後在 val 上做溫度校準（LBFGS 最小化 NLL），存模型 + label map + 溫度 + meta。

前置：系統 Python（GPU torch + transformers + datasets + accelerate）。
用法：
    python scripts/train_classifier.py --task sentiment \
        --gold data/gold/gold.jsonl --silver data/silver/silver_sentiment.jsonl \
        --epochs 3 --out models/sentiment-zh --mlflow
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

from ml.annotation import load_jsonl  # noqa: E402
from ml.metrics import classification_metrics  # noqa: E402

# 每個任務固定的標籤順序（id 對應）。sentiment 對齊 sentiment.py；theme 對齊 theme.py。
LABELS = {  # theme 對齊 ml.annotation.THEME_LABELS / theme.py
    "sentiment": ["negative", "neutral", "positive"],
    "theme": ["新工具", "模型動態", "使用方法", "風險限制", "倫理法規", "其他"],
}
# gold 記錄裡，各任務的標籤欄位名。
_GOLD_FIELD = {"sentiment": "sentiment", "theme": "theme"}


def _load_examples(path: Path | None, task: str, *, round1_only: bool) -> list[tuple[str, str]]:
    """從 JSONL 載 (text, label)；只收 label 屬於該任務合法標籤者。"""
    if not path:
        return []
    field = _GOLD_FIELD[task]
    valid = set(LABELS[task])
    out: list[tuple[str, str]] = []
    for r in load_jsonl(path):
        if round1_only and r.get("round", 1) != 1:
            continue
        label = r.get(field) or r.get("label")  # gold 用任務欄位；silver 用 'label'
        text = r.get("text", "")
        if label in valid and text:
            out.append((text, label))
    return out


def fit_temperature(logits, labels, torch) -> float:
    """溫度校準（Guo 2017）：在 val logits 上 LBFGS 最小化 NLL，回傳純量 T。"""
    T = torch.nn.Parameter(torch.ones(1, device=logits.device))  # noqa: N806 — 溫度符號 T（Guo 2017）
    nll = torch.nn.CrossEntropyLoss()
    opt = torch.optim.LBFGS([T], lr=0.01, max_iter=60)

    def closure():
        opt.zero_grad()
        loss = nll(logits / T.clamp_min(1e-3), labels)
        loss.backward()
        return loss

    opt.step(closure)
    return max(float(T.detach().cpu().item()), 1e-3)


def main() -> None:
    ap = argparse.ArgumentParser(description="微調 chinese-macbert 分類器")
    ap.add_argument("--task", choices=["sentiment", "theme"], required=True)
    ap.add_argument("--gold", type=Path, default=None, help="gold JSONL（人工驗證，當 val）")
    ap.add_argument("--silver", type=Path, default=None, help="silver JSONL（Qwen 蒸餾，當 train）")
    ap.add_argument("--base-model", default="hfl/chinese-macbert-base")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--lr", type=float, default=2e-5)
    ap.add_argument("--max-length", type=int, default=256)
    ap.add_argument("--val-frac", type=float, default=0.2, help="無 gold 時，從 silver 切多少當 val")
    ap.add_argument("--out", type=Path, required=True, help="模型輸出目錄")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--mlflow", action="store_true", help="記錄到 MLflow")
    args = ap.parse_args()

    # 載入任何會連外的東西之前先注入 OS 信任庫（企業/校園 TLS 攔截下下載模型不噴 SSL）。
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

    import numpy as np
    import torch
    from datasets import Dataset
    from transformers import (
        AutoModelForSequenceClassification,
        AutoTokenizer,
        DataCollatorWithPadding,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    set_seed(args.seed)
    labels = LABELS[args.task]
    label2id = {lbl: i for i, lbl in enumerate(labels)}
    id2label = dict(enumerate(labels))

    gold = _load_examples(args.gold, args.task, round1_only=True)
    silver = _load_examples(args.silver, args.task, round1_only=False)

    # gold = 乾淨 val；silver = train。無 silver 則用 gold 切分。
    if silver and gold:
        train_ex, val_ex = silver, gold
    elif silver:
        rng = np.random.default_rng(args.seed)
        idx = rng.permutation(len(silver))
        cut = int(len(silver) * (1 - args.val_frac))
        train_ex = [silver[i] for i in idx[:cut]]
        val_ex = [silver[i] for i in idx[cut:]]
        print("⚠️ 無 gold：改用 silver 切分 train/val（評估會偏樂觀，正式評估請用 gold）。")
    elif gold:
        rng = np.random.default_rng(args.seed)
        idx = rng.permutation(len(gold))
        cut = int(len(gold) * (1 - args.val_frac))
        train_ex = [gold[i] for i in idx[:cut]]
        val_ex = [gold[i] for i in idx[cut:]]
        print("⚠️ 無 silver：用 gold 切分訓練（樣本可能很少）。")
    else:
        sys.exit("❌ gold 與 silver 都沒有資料，無法訓練。先跑 annotate.py / distill_labels.py。")

    print(f"📊 task={args.task} · train={len(train_ex)} · val={len(val_ex)} · labels={labels}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)

    def _to_ds(examples: list[tuple[str, str]]) -> "Dataset":
        texts = [t for t, _ in examples]
        ys = [label2id[lbl] for _, lbl in examples]
        enc = tokenizer(texts, truncation=True, max_length=args.max_length)
        enc["labels"] = ys
        return Dataset.from_dict(enc)

    train_ds, val_ds = _to_ds(train_ex), _to_ds(val_ex)

    model = AutoModelForSequenceClassification.from_pretrained(
        args.base_model, num_labels=len(labels), id2label=id2label, label2id=label2id
    )

    def compute_metrics(eval_pred) -> dict:
        logits, gold_ids = eval_pred
        pred_ids = np.asarray(logits).argmax(axis=-1)
        y_true = [id2label[int(i)] for i in gold_ids]
        y_pred = [id2label[int(i)] for i in pred_ids]
        m = classification_metrics(y_true, y_pred, labels)
        return {
            "f1_macro": m["f1_macro"],
            "f1_weighted": m["f1_weighted"],
            "accuracy": m["accuracy"],
        }

    targs = TrainingArguments(
        output_dir=str(args.out / "_hf"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=max(args.batch_size, 32),
        learning_rate=args.lr,
        eval_strategy="epoch",
        save_strategy="no",
        logging_steps=50,
        seed=args.seed,
        report_to=[],
    )
    # 動態 padding：tokenize 時未 pad（變長序列），交給 collator 逐批 pad 到該批最長，省記憶體。
    # （不加會踩 default_data_collator 對不等長序列 torch.tensor 失敗的 bug。）
    data_collator = DataCollatorWithPadding(tokenizer)
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        compute_metrics=compute_metrics,
        data_collator=data_collator,
    )
    trainer.train()

    # 最終 val 預測 → 指標 + 溫度校準（Guo 2017）。
    pred = trainer.predict(val_ds)
    val_metrics = compute_metrics((pred.predictions, pred.label_ids))
    device = model.device
    logits_t = torch.tensor(pred.predictions, dtype=torch.float32, device=device)
    labels_t = torch.tensor(pred.label_ids, dtype=torch.long, device=device)
    temperature = fit_temperature(logits_t, labels_t, torch)
    print(f"✅ val: f1_macro={val_metrics['f1_macro']:.3f} · acc={val_metrics['accuracy']:.3f} · T={temperature:.3f}")

    # 存模型 + tokenizer + meta（label 順序、溫度、base、指標）。
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    meta = {
        "task": args.task,
        "labels": labels,
        "base_model": args.base_model,
        "temperature": temperature,
        "val_metrics": val_metrics,
        "n_train": len(train_ex),
        "n_val": len(val_ex),
    }
    (args.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 模型已存：{args.out}（meta.json 含 label 順序與溫度 T）")

    if args.mlflow:
        import mlflow

        mlflow.set_experiment(f"pulse-{args.task}")
        with mlflow.start_run():
            mlflow.log_params({
                "task": args.task, "base_model": args.base_model, "epochs": args.epochs,
                "batch_size": args.batch_size, "lr": args.lr, "max_length": args.max_length,
                "n_train": len(train_ex), "n_val": len(val_ex),
            })
            mlflow.log_metrics({**val_metrics, "temperature": temperature})
            mlflow.log_artifact(str(args.out / "meta.json"))
        print("📈 已記錄到 MLflow。")


if __name__ == "__main__":
    main()
