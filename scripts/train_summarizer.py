"""
LoRA / QLoRA 微調忠實事件摘要器 —— Qwen2.5-7B-Instruct（預設）或 1.5B（事件摘要 B 線 Step 3）。

對應 A 線的 `train_classifier.py`。把已建好的「抽取→改寫＋強制引註」prompt（重用
`ml.summarize.build_summary_prompt`，保證訓練 prompt == 推論 prompt）配上目標摘要，做
監督式微調（SFT），讓模型專一化於此單一任務（Hu 2021 LoRA；Dettmers 2023 QLoRA；案例研究 §5、Step 3）。

模型大小與記憶體（單張 8GB RTX 4060）：
- 7B（預設，對齊現有 qwen2.5:7b baseline）：bf16 全權重 ~14GB 放不進 8GB → **必須 QLoRA（4-bit）**，
  預設即開 `--load-4bit`（NF4 + double-quant + bf16 compute，Dettmers 2023）。需 `bitsandbytes`。
- 1.5B：bf16 一般 LoRA 即可放下 → 跑時加 `--base-model Qwen/Qwen2.5-1.5B-Instruct --no-load-4bit`。

設計選擇（為何 peft + transformers Trainer，不用 trl）：
- completion-only 損失自己遮罩（prompt 段 label=-100，只在「事件摘要」本文算 loss），
  比追 trl 各版本變動的 API 穩；4-bit 走 peft 的 prepare_model_for_kbit_training。

資料分工（對齊 annotation-guidelines §7 / train_classifier 同風格）：
- silver（Qwen 生成→faithfulness 過濾）→ 訓練集；可用 --min-faithfulness 濾掉低分樣本。
- gold（人工後編修）→ held-out val（不進訓練）；無 gold 則從 silver 切 val。

訓練資料格式（JSONL，一列一事件）：
    {"key_sentences": [{"text": "...", "source_id": 1, "source": "Threads"}, ...],
     "summary": "OpenAI 發表 GPT-5 [1]。價格與前代相同 [2]。",
     "faithfulness_score": 0.83,            # 可選；silver 過濾用
     "max_sentences": 8, "lang": "zh-Hant"}  # 可選；缺省用 CLI 預設

前置：系統 Python（GPU torch + transformers + datasets + accelerate + peft）。
    pip install peft bitsandbytes   # bitsandbytes 為 7B QLoRA 必需（1.5B 一般 LoRA 可不裝）
    # 7B 的 HF 權重（~15GB）首次會自動下載；Ollama 的 GGUF 不能直接拿來 HF 訓練。
用法（7B QLoRA，預設）：
    python scripts/train_summarizer.py \
        --silver data/silver/summaries.jsonl --gold data/gold/summaries.jsonl \
        --epochs 3 --out models/summarizer-lora --offline
用法（1.5B 一般 LoRA）：
    python scripts/train_summarizer.py --base-model Qwen/Qwen2.5-1.5B-Instruct --no-load-4bit ...
"""
import argparse
import json
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "ml"))

from ml.annotation import load_jsonl  # noqa: E402
from ml.summarize import build_summary_prompt  # noqa: E402 — 重用同一份 prompt（訓練==推論）

# Qwen2.5（LLaMA 式）注意力 + MLP 的線性層名稱：LoRA 掛在這些 proj 上。
_QWEN_LORA_TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def _load_records(path: Path | None, min_faith: float) -> list[dict]:
    """載入摘要訓練列，過濾掉缺 key_sentences/summary 或忠實度低於門檻者。"""
    if not path:
        return []
    out: list[dict] = []
    for r in load_jsonl(path):
        ks = r.get("key_sentences")
        summary = (r.get("summary") or "").strip()
        if not ks or not summary:
            continue
        if min_faith > 0 and float(r.get("faithfulness_score", 1.0)) < min_faith:
            continue
        out.append(r)
    return out


def _build_pairs(records: list[dict], default_max_sent: int, default_lang: str) -> list[tuple[str, str]]:
    """每列 → (prompt, completion)。prompt 由 build_summary_prompt 重建（與推論同一份）。"""
    pairs: list[tuple[str, str]] = []
    for r in records:
        prompt = build_summary_prompt(
            r["key_sentences"],
            max_sentences=int(r.get("max_sentences", default_max_sent)),
            lang=str(r.get("lang", default_lang)),
        )
        pairs.append((prompt, r["summary"].strip()))
    return pairs


def _encode(pair: tuple[str, str], tokenizer, max_length: int) -> dict:
    """組 input_ids/labels：labels 在 prompt 段設 -100（completion-only loss），結尾補 EOS。
    過長則「只」從 prompt 前段砍（保住完整 completion 與結尾的『事件摘要：』提示）。"""
    prompt, completion = pair
    eos = tokenizer.eos_token_id
    p_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    c_ids = tokenizer(completion, add_special_tokens=False)["input_ids"] + [eos]
    # 保完整 completion；prompt 太長就砍掉前面（指令開頭），留靠近摘要提示的尾段。
    budget = max_length - len(c_ids)
    if budget < 1:  # completion 本身就超長 → 退而硬截（極少見）
        c_ids = c_ids[: max_length - 1] + [eos]
        budget = 0
    if len(p_ids) > budget:
        p_ids = p_ids[len(p_ids) - budget :]
    input_ids = p_ids + c_ids
    labels = [-100] * len(p_ids) + c_ids  # 只在 completion 上算 loss
    return {"input_ids": input_ids, "labels": labels, "attention_mask": [1] * len(input_ids)}


def _resolve_resume(resume: str | None, output_dir: Path) -> str | bool | None:
    """把 --resume-from-checkpoint 轉成 Trainer.train 接受的值。
    None→不續跑；'auto'→True（HF 自動找最後 checkpoint，無則回 None）；否則→該路徑字串。"""
    if not resume:
        return None
    if resume.lower() == "auto":
        has_ckpt = output_dir.is_dir() and any(output_dir.glob("checkpoint-*"))
        if not has_ckpt:
            print(f"ℹ️ --resume-from-checkpoint auto：{output_dir} 下無 checkpoint，從頭訓練。")
            return None
        return True
    return resume


def _run_train(trainer, resume: str | bool | None) -> None:
    """跑訓練，把 OOM / 中斷轉成可讀錯誤而非裸 traceback（呼應靜默死在 94% 的事故）。"""
    try:
        trainer.train(resume_from_checkpoint=resume)
    except RuntimeError as e:
        msg = str(e).lower()
        if "out of memory" in msg or ("cuda" in msg and "memory" in msg):
            sys.exit(
                "❌ GPU 記憶體不足（OOM）。7B QLoRA 在 8GB 卡上建議：調小 --max-length（如 768/640）、"
                "確認 --load-4bit 開著、--batch-size 1 靠 --grad-accum 補；最近 checkpoint 已存於 "
                "output_dir，可 --resume-from-checkpoint auto 續跑。原始錯誤：" + str(e)
            )
        raise
    except KeyboardInterrupt:
        sys.exit(
            "\n⏹️ 訓練被中斷。最近一個 epoch 的 LoRA checkpoint 已存於 output_dir，"
            "下次可 --resume-from-checkpoint auto 續跑（不必從頭）。"
        )


def main() -> None:
    ap = argparse.ArgumentParser(description="LoRA 微調 Qwen2.5-1.5B 忠實事件摘要器")
    ap.add_argument("--silver", type=Path, default=None, help="silver JSONL（訓練集）")
    ap.add_argument("--gold", type=Path, default=None, help="gold JSONL（held-out val）")
    ap.add_argument("--base-model", default="Qwen/Qwen2.5-7B-Instruct")
    ap.add_argument(
        "--load-4bit", action=argparse.BooleanOptionalAction, default=True,
        help="QLoRA 4-bit 量化（7B 在 8GB 卡上必開；1.5B 可 --no-load-4bit 走一般 LoRA）",
    )
    ap.add_argument("--out", type=Path, required=True, help="LoRA adapter 輸出目錄")
    ap.add_argument("--epochs", type=float, default=3.0)
    ap.add_argument("--batch-size", type=int, default=1, help="per-device；8GB 卡建議 1，靠 grad-accum 補")
    ap.add_argument("--grad-accum", type=int, default=16, help="梯度累積步數（有效 batch = batch-size × 此值）")
    ap.add_argument("--lr", type=float, default=2e-4, help="LoRA 慣用較大 lr")
    ap.add_argument("--max-length", type=int, default=896, help="7B QLoRA 在 8GB 上的保守上限；OOM 再調小")
    ap.add_argument("--val-frac", type=float, default=0.1, help="無 gold 時從 silver 切多少當 val")
    ap.add_argument("--min-faithfulness", type=float, default=0.0, help="silver 過濾：低於此忠實度分丟棄")
    ap.add_argument("--max-sentences", type=int, default=8, help="prompt 預設句數上限（列內可覆寫）")
    ap.add_argument("--lang", default="zh-Hant")
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--lora-dropout", type=float, default=0.05)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--resume-from-checkpoint", default=None,
        help="從 checkpoint 續跑：傳 checkpoint 目錄，或 'auto' 自動找 output_dir 下最後一個。"
             "7B QLoRA 訓練長，中斷/OOM 後靠此續跑（呼應 theme 第三訓靜默死在 94% 的事故）",
    )
    ap.add_argument(
        "--save-total-limit", type=int, default=2,
        help="最多保留幾個 checkpoint（含 best），其餘自動清掉省碟",
    )
    ap.add_argument("--mlflow", action="store_true")
    ap.add_argument("--offline", action="store_true", help="完全離線（base model 已快取時用）")
    args = ap.parse_args()

    if args.offline:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"

    # 連外前注入 OS 信任庫（校園/企業 TLS 攔截下下載權重不噴 SSL）。
    try:
        import truststore

        truststore.inject_into_ssl()
    except ImportError:
        pass

    import random

    import numpy as np
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        Trainer,
        TrainingArguments,
        set_seed,
    )

    # 可重現：set_seed 一併設 random/numpy/torch(+cuda)；下面顯式再設一次（不留隱性隨機）。
    set_seed(args.seed)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    silver = _load_records(args.silver, args.min_faithfulness)
    gold = _load_records(args.gold, 0.0)
    if not silver and not gold:
        sys.exit("❌ silver 與 gold 都沒有資料。先跑 silver 生成腳本 / 標 gold。")

    # gold = 乾淨 val；silver = train。無 gold 則從 silver 切。
    if silver and gold:
        train_rec, val_rec = silver, gold
    elif silver:
        rng = np.random.default_rng(args.seed)
        idx = rng.permutation(len(silver))
        cut = max(1, int(len(silver) * (1 - args.val_frac)))
        train_rec = [silver[i] for i in idx[:cut]]
        val_rec = [silver[i] for i in idx[cut:]] or [silver[i] for i in idx[:1]]
        print("⚠️ 無 gold：改用 silver 切分 train/val（正式忠實度評估請用 gold + evaluate_summaries.py）。")
    else:
        rng = np.random.default_rng(args.seed)
        idx = rng.permutation(len(gold))
        cut = max(1, int(len(gold) * (1 - args.val_frac)))
        train_rec = [gold[i] for i in idx[:cut]]
        val_rec = [gold[i] for i in idx[cut:]] or [gold[i] for i in idx[:1]]
        print("⚠️ 無 silver：用 gold 切分訓練（樣本可能很少，僅供 smoke test）。")

    train_pairs = _build_pairs(train_rec, args.max_sentences, args.lang)
    val_pairs = _build_pairs(val_rec, args.max_sentences, args.lang)
    print(f"📊 summarizer · train={len(train_pairs)} · val={len(val_pairs)} · base={args.base_model}")

    tokenizer = AutoTokenizer.from_pretrained(args.base_model)
    if tokenizer.pad_token_id is None:  # Qwen 多數版本有 pad；保險起見退回 eos
        tokenizer.pad_token = tokenizer.eos_token

    def _to_ds(pairs: list[tuple[str, str]]) -> "Dataset":
        rows = [_encode(p, tokenizer, args.max_length) for p in pairs]
        return Dataset.from_list(rows)

    train_ds, val_ds = _to_ds(train_pairs), _to_ds(val_pairs)

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    if args.load_4bit:
        # QLoRA（Dettmers 2023）：NF4 + double-quant，compute 維持 bf16/fp16。
        bnb = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=dtype,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.base_model, quantization_config=bnb, torch_dtype=dtype, device_map={"": 0}
        )
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    else:
        model = AutoModelForCausalLM.from_pretrained(args.base_model, torch_dtype=dtype)
    model.config.use_cache = False  # 與 gradient checkpointing 並用必關
    if model.config.pad_token_id is None:
        model.config.pad_token_id = tokenizer.pad_token_id

    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=_QWEN_LORA_TARGETS,
    )
    model = get_peft_model(model, lora)
    model.print_trainable_parameters()
    # gradient checkpointing：4-bit 已由 prepare_model_for_kbit_training 啟用（含 input require grads）；
    # 一般 LoRA 路在此手動開，並讓輸入需要梯度（否則 checkpoint 區塊梯度不回流）。
    if not args.load_4bit:
        model.gradient_checkpointing_enable()
        model.enable_input_require_grads()

    def collate(features: list[dict]) -> dict:
        """右 padding：input_ids/attention_mask 補 pad，labels 補 -100（被忽略）。"""
        max_len = max(len(f["input_ids"]) for f in features)
        pad_id = tokenizer.pad_token_id
        batch = {"input_ids": [], "attention_mask": [], "labels": []}
        for f in features:
            n = max_len - len(f["input_ids"])
            batch["input_ids"].append(f["input_ids"] + [pad_id] * n)
            batch["attention_mask"].append(f["attention_mask"] + [0] * n)
            batch["labels"].append(f["labels"] + [-100] * n)
        return {k: torch.tensor(v, dtype=torch.long) for k, v in batch.items()}

    targs = TrainingArguments(
        output_dir=str(args.out / "_hf"),
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        gradient_accumulation_steps=args.grad_accum,
        # gc 已在模型上手動啟用（兩路皆然）→ 這裡不再交給 Trainer，避免重複包裝。
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        bf16=(dtype == torch.bfloat16),
        fp16=(dtype == torch.float16),
        # 4-bit 用 paged 8-bit optimizer 省顯存（需 bitsandbytes）；一般路用標準 AdamW。
        optim="paged_adamw_8bit" if args.load_4bit else "adamw_torch",
        eval_strategy="epoch",
        # 每 epoch 存 LoRA checkpoint + 結束載回最佳（依 eval_loss，越低越好）。7B QLoRA 訓練長，
        # 中斷/OOM 後可 --resume-from-checkpoint 續跑，不再像 theme 第三訓靜默死在 94% 卻無 checkpoint。
        save_strategy="epoch",
        save_total_limit=args.save_total_limit,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=10,
        seed=args.seed,
        report_to=[],
    )
    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        data_collator=collate,
    )
    _run_train(trainer, _resolve_resume(args.resume_from_checkpoint, args.out / "_hf"))

    eval_metrics = trainer.evaluate()
    val_loss = float(eval_metrics.get("eval_loss", float("nan")))
    ppl = float(np.exp(val_loss)) if val_loss == val_loss else float("nan")  # nan-safe
    print(f"✅ val_loss={val_loss:.4f} · perplexity≈{ppl:.2f}")

    # 存 LoRA adapter（peft 只存增量權重，小）+ tokenizer + meta。
    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    meta = {
        "task": "event_summarizer",
        "base_model": args.base_model,
        "load_4bit": args.load_4bit,
        "lora": {"r": args.lora_r, "alpha": args.lora_alpha, "dropout": args.lora_dropout,
                 "target_modules": _QWEN_LORA_TARGETS},
        "val_loss": val_loss,
        "perplexity": ppl,
        "n_train": len(train_pairs),
        "n_val": len(val_pairs),
        "min_faithfulness": args.min_faithfulness,
        "max_length": args.max_length,
    }
    (args.out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"💾 LoRA adapter 已存：{args.out}（meta.json 含 base/lora 設定與 val_loss）")
    print("   推論：用 peft 把 adapter 疊回 base，或合併後轉 GGUF 餵 Ollama（見 evaluate_summaries.py bake-off）。")

    if args.mlflow:
        import mlflow

        mlflow.set_experiment("pulse-summarizer")
        with mlflow.start_run():
            mlflow.log_params({
                "base_model": args.base_model, "epochs": args.epochs, "lr": args.lr,
                "lora_r": args.lora_r, "lora_alpha": args.lora_alpha,
                "n_train": len(train_pairs), "n_val": len(val_pairs),
            })
            mlflow.log_metrics({"val_loss": val_loss, "perplexity": ppl})
            mlflow.log_artifact(str(args.out / "meta.json"))
        print("📈 已記錄到 MLflow。")


if __name__ == "__main__":
    main()
