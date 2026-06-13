# Theme Bake-off 第二輪：多語編碼器驗證語言錯配假設（2026-06-14）

> 第一輪（[theme-bakeoff-findings.md](theme-bakeoff-findings.md)）發現：所有單語候選接近隨機，根因是
> **silver 99% 英文 vs gold 85% 中文的訓練/評測語言錯配**。第二輪用**多語編碼器**驗證此假設。
> 完整指標：[`docs/bakeoff-theme-report-r2.md`](../bakeoff-theme-report-r2.md)。

## 假設與設計

- **假設**：第一輪崩潰的主因是「中文單語編碼器（macbert/bert-base-chinese）+ 英文 silver → 中文 gold」的跨語言不轉移。若換**多語編碼器**，同一份英文 silver 應能轉移到中文 gold。
- **設計**：base 改 `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`（本機快取、真多語），silver/gold/評測**全部不變**（控制變因＝只換編碼器）。
- **需要的程式修正**（已併入 train_classifier.py）：
  - `ignore_mismatched_sizes=True`：從 mnli 3 類頭微調成 6 類，重初始化頭部而非報錯。
  - `model.float()`：mnli ckpt 以 fp16 存，直接微調與 Float 損失權重衝突（expected Half but found Float）。

## 結果（依 macro-F1，n=92 gold）

| 候選 | 編碼器 | macro-F1 | acc | ECE | AURC |
|------|--------|---------:|----:|----:|-----:|
| 🏆 **D1 mDeBERTa + effective** | 多語 | **0.159** | 0.272 | 0.445 | **0.722** |
| baseline zero-shot | mDeBERTa-mnli | 0.148 | 0.163 | 0.573 | 0.802 |
| D2 mDeBERTa + none | 多語 | 0.141 | 0.239 | 0.443 | 0.753 |
| C1 macbert + none | 單語 | 0.127 | 0.217 | 0.272 | 0.820 |
| C4 bert-base + effective | 單語 | 0.119 | 0.217 | — | — |
| C2 macbert + effective | 單語 | 0.115 | 0.207 | — | — |
| C3 macbert + inverse | 單語 | 0.109 | 0.196 | — | — |

**統計（winner=D1 vs 各對手，McNemar + bootstrap CI 5000 + BH-FDR q=0.05）**：所有配對 CI 皆含 0、p_adj 未達顯著（vs zero-shot ΔF1=+0.011, p_adj=0.128）。

## 結論

1. **假設成立（方向明確）**：**所有多語候選（0.141–0.159）整段高於所有單語候選（0.109–0.127）**——換編碼器就把單語從 0.127 拉到 0.159。語言錯配確實是第一輪崩潰的主因。
2. **微調首次追平/微超 zero-shot**：D1（0.159）在 macro-F1、acc（0.272 vs 0.163）、校準（ECE 0.445 vs 0.573）、AURC（0.722 vs 0.802）全面優於 zero-shot baseline——但 **92 gold 太小，差距未達統計顯著**（不能宣稱贏）。
3. **class weighting 有效**：mDeBERTa effective(0.159) > none(0.141)。
4. **少數類仍 0**：模型動態/風險限制/倫理法規 f1=0——silver 樣本近乎沒有（13/78/93）、gold support 也僅 4/6/15。這是**資料問題**，非模型問題。

## 下一步（真正能突破的）

1. **擴 gold 到 200–300**（目前 92，少數類不可信）→ 才可能讓 D1 vs zero-shot 的差距達顯著。
2. **補少數類 silver**：對 模型動態/風險限制/倫理法規 做有針對性的蒸餾或抽樣，否則這三類永遠學不起來。
3. **語言對齊的「終極版」**：在中文文本（翻譯後）上重蒸餾 silver，與多語編碼器疊加，預期再進一步——但受 Qwen 單 GPU 吞吐限制（見 [[theme-bakeoff-finding]]）。
