# Theme Bake-off 第三輪：語言對齊中文 silver — 首個顯著勝出 zero-shot 的模型（2026-06-14）

> 三輪 Offline Evaluation 的收斂點：微調模型**首次統計顯著**勝過 zero-shot baseline。
> 完整指標：[`docs/bakeoff-theme-report-r3.md`](../bakeoff-theme-report-r3.md)。

## 三輪演進（同一 gold=92、同一統計協定）

| 輪次 | 做法 | 最佳 macro-F1 | vs zero-shot(0.148) |
|------|------|--------------:|---------------------|
| R1 | 單語編碼器(macbert) + 英文 silver | 0.127 | 輸，且全部統計平手 |
| R2 | **多語編碼器**(mDeBERTa) + 英文 silver | 0.159 | 微超但**未顯著** |
| R3 | 多語編碼器 + **語言對齊中文 silver** | **0.288** | **+0.140，p_adj<0.001，顯著勝出 ✓** |

每一輪都由評測診斷出下一步：R1 發現語言錯配 → R2 換多語編碼器（確認是編碼器+語言問題）→ R3 蒸餾中文 silver（語言對齊 + 少數類豐富）。

## R3 Bake-off 結果（n=92 gold）

| 候選 | macro-F1 | acc | ECE | AURC |
|------|---------:|----:|----:|-----:|
| 🏆 **E1 mDeBERTa + 純中文 silver** | **0.288** | 0.457 | **0.068** | **0.488** |
| E2 mDeBERTa + 中英混合 | 0.218 | 0.348 | 0.195 | 0.603 |
| D1 mDeBERTa + 英文 silver (R2) | 0.159 | 0.272 | 0.445 | 0.722 |
| baseline zero-shot | 0.148 | 0.163 | 0.573 | 0.802 |

**統計檢定（winner=E1，McNemar + bootstrap CI 5000 + BH-FDR q=0.05）**：
- **vs zero-shot：ΔF1=+0.140，CI[+0.031,+0.251]（不含 0），p_adj<0.001 → 顯著優於 ✓**
- **vs D1（英文 silver）：ΔF1=+0.129，CI[+0.053,+0.202]，p_adj=0.003 → 顯著優於 ✓**
- vs E2（混合）：ΔF1=+0.070，p_adj=0.100 → 未達顯著

## 關鍵發現

1. **語言對齊是決定性因素**：同樣多語編碼器、同樣 effective 加權，只把 silver 從英文換成語言對齊的中文，macro-F1 從 0.159 → 0.288（近兩倍），且**首次顯著勝過 zero-shot**。
2. **純中文 > 中英混合**：E1(0.288) > E2(0.218)。加英文 silver 反而稀釋（英文與中文 gold 的領域/語言差異拖累），純語言對齊資料勝出。
3. **校準大幅改善**：E1 ECE=0.068（zero-shot 0.573）、溫度 T≈1.05（近乎天然校準）、AURC 0.488（zero-shot 0.802）——不只準，信心也可靠。
4. **少數類部分救起**：倫理法規 f1 從 0 → 0.235（116 筆中文 silver 生效）；但**模型動態(gold support=4)、風險限制(=6) 仍 0**——這是 **gold 樣本不足**，非模型問題。

## 下一步

1. **採用 E1 上線**：把 `models/theme-e1-zh-effective` 接進 `scripts/backfill_themes.py` / 每日流程，取代 zero-shot mDeBERTa；在 `evaluation_runs` 記錄此次升級（完成「離線評測 → 上線」閉環）。
2. **擴 gold 救剩餘少數類**：模型動態/風險限制 gold 各僅 4/6 筆，指標不可信。用 `data/gold/minority_queue.jsonl`（407 個少數類候選）人工標到每類 ≥20，才能可靠評估並進一步提升。
3. 蒸餾更多中文 silver（目前 1,858）+ 補少數類，重訓可望再進步。
