# Theme 分類器 Bake-off 發現報告（2026-06-13）

> 多候選 Offline Evaluation bake-off。重點不是「哪個模型贏」，而是 **bake-off 抓出了一個資料管線缺陷**。
> 機器產出的完整指標 JSON/報告：[`docs/bakeoff-theme-report.md`](../bakeoff-theme-report.md)。
> 可重現訓練腳本：[`scripts/_bakeoff_train.sh`](../../scripts/_bakeoff_train.sh)。

## 設定

- **任務**：theme 6 類（新工具 / 模型動態 / 使用方法 / 風險限制 / 倫理法規 / 其他）
- **硬體**：單張 RTX 4060 Laptop（8GB）→ 候選**序列化**訓練（無法平行，會 OOM）
- **gold（val/eval）**：92 筆人工標註（來源 threads 37 · ptt 36 · devto 19；6 類齊全但少數類極稀）
- **silver（train）**：`data/silver/theme.jsonl` 51,406 筆 Qwen 蒸餾標籤 → 封頂每類 ≤6000 得 14,532 筆（同時緩解偏斜）
- **候選矩陣**（全用本機快取 base + `--offline`，3 epoch，seed=42）：

| 候選 | base 編碼器 | class-weights |
|------|------------|---------------|
| C1 | hfl/chinese-macbert-base | none |
| C2 | hfl/chinese-macbert-base | effective (Cui 2019) |
| C3 | hfl/chinese-macbert-base | inverse |
| C4 | bert-base-chinese | effective |
| baseline | mDeBERTa-v3 zero-shot（現行生產法，免訓練） | — |

## 結果（依 macro-F1，n=92）

| 候選 | macro-F1 | acc | wF1 | ECE | AURC |
|------|---------:|----:|----:|----:|-----:|
| 🏆 baseline-zeroshot | **0.148** | 0.163 | 0.169 | 0.573 | 0.802 |
| C1 macbert-none | 0.127 | 0.217 | 0.224 | 0.272 | 0.820 |
| C4 bertbase-effective | 0.119 | 0.217 | 0.196 | 0.267 | 0.817 |
| C2 macbert-effective | 0.115 | 0.207 | 0.192 | 0.313 | 0.791 |
| C3 macbert-inverse | 0.109 | 0.196 | 0.179 | 0.271 | 0.797 |

**統計顯著性（winner vs 各對手，McNemar + macro-F1 差 bootstrap CI 5000 + BH-FDR q=0.05）**：
所有配對 ΔmacroF1 的 95% CI **皆含 0**、McNemar p_adj ≈ 0.64 → **全部統計上平手，無顯著贏家**。

## 根因：訓練/評測語言錯配（bake-off 抓到的真問題）

絕對值低到接近隨機（acc 0.21 < 多數類「其他」基線 0.40），不是調參能解的。診斷出根因：

| 資料 | 平均中文字（CJK）比例 | 語言 |
|------|---------------------:|------|
| silver（訓練）| **0.00** | **99% 英文**（<5% CJK 共 14,450/14,532） |
| gold（評測）| **0.48** | **85% 中文**（>30% CJK 共 79/92） |

- silver 是在**英文為主的 HN/Devto 量體**（52k+6.4k）上蒸餾的，文本幾乎全英文。
- gold 幾乎全中文：threads/ptt 為母語繁中；連 devto 那 19 筆 gold 的 `text` 也是**翻譯後中文**（cjk 0.45）。
- 我們等於拿**英文**訓練**中文 BERT 編碼器**，再用**中文**評測 → 跨語言不轉移，所有候選一起崩。class-weighting / 編碼器差異被這個更大的錯配淹沒（故四候選全平手）。

**這是 Offline Evaluation 的價值示範**：嚴謹的多候選 + 統計檢定，把「微調沒贏 zero-shot」的表象，追到「silver 蒸餾語言與產品/評測語言錯配」的資料管線根因——而不是繼續瞎調超參。

## 建議的下一步實驗（真正有意義的迭代）

1. **對齊語言**：theme silver 改在**中文文本**上蒸餾——用管線既有的 EN→ZH 翻譯結果（feed 已在翻譯）當 silver 輸入，使 train 與 gold 同語言；或
2. **多語編碼器**：若要保留英文 silver 量體，base 改用多語模型（mDeBERTa / xlm-roberta）並讓 gold 也納入英文原文，避免單語錯配；
3. 兩者擇一後**重跑同一 bake-off**（腳本與評測不變），看微調是否終於顯著勝出 zero-shot。

## 限制

- gold 僅 92 筆、少數類（模型動態 4 / 新工具 6 / 風險限制 6）指標不可信——即使修了語言，仍需擴標 gold（目標 200–300）才能下顯著結論。
- 本輪未納入 Qwen few-shot 候選（Ollama CUDA build 已知會 crash）。
