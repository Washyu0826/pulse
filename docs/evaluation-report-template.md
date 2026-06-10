# Offline Evaluation 報告範本（bake-off run）

> 一次 bake-off（多候選在同一 gold set 上的配對比較）的可重複報告範本。複製本檔、把 `_TBD_` / `<...>` 佔位填掉。
>
> 對應程式：`scripts/evaluate.py`（N 候選 bake-off）、`ml/ml/metrics.py`（指標）、`evaluation_runs` 表（歷史紀錄）。
>
> **這不是線上 A/B**（無使用者流量分流），是 Offline Evaluation——多模型在同一份 labeled set 的配對比較（見 ADR-008）。

---

## 0. Run 中繼資料

| 欄位 | 值 |
|------|-----|
| 任務（task） | `<sentiment \| theme \| 摘要忠實度>` |
| 日期 | `<YYYY-MM-DD>` |
| Gold set 版本 | `<gold_zh_v1>` |
| 主指標 | `<macro-F1 \| faithfulness_score>` |
| MLflow run id | `<...>` |
| 指令 | `python scripts/evaluate.py --task <...> --gold <...> --models <...> [--with-qwen] [--mlflow]` |

---

## 1. 候選（candidates）

| 代號 | 模型 / 做法 | 備註 |
|------|-------------|------|
| baseline | `<英文 twitter-roberta / mDeBERTa zero-shot / Qwen-only>` | 對照基準 |
| cand-1 | `<models/theme-macbert>` | `<base / 訓練資料>` |
| cand-2 | `<...>` | `<...>` |

---

## 2. Gold set 統計

| 項目 | 值 |
|------|-----|
| 樣本數 | `_TBD_` |
| 標註者 self-consistency Cohen's κ | `_TBD_`（目標 > 0.8） |
| κ bootstrap 95% CI | [`_TBD_`, `_TBD_`] |
| 語言分布（繁中 / 其他） | `_TBD_` |

各類別分布：

```
<label>: <n>  (xx.x%)
<label>: <n>  (xx.x%)
...
```

---

## 3. macro-F1 排名

> 依主指標由高到低。winner 取第一名。

| 排名 | 候選 | macro-F1 | weighted-F1 | accuracy |
|------|------|----------|-------------|----------|
| 1 (winner) | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |
| 2 | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |
| 3 | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |

Per-class P / R / F1（winner）：

```
<label>   P=_TBD_  R=_TBD_  F1=_TBD_  (support=_TBD_)
<label>   P=_TBD_  R=_TBD_  F1=_TBD_  (support=_TBD_)
...
```

Confusion matrix（winner，rows=true、cols=pred）：

```
            pred_a  pred_b  pred_c
true_a       _TBD_   _TBD_   _TBD_
true_b       _TBD_   _TBD_   _TBD_
true_c       _TBD_   _TBD_   _TBD_
```

---

## 4. 統計顯著性（winner vs 每個對手）

> McNemar（accuracy，配對）+ macro-F1 差的 paired bootstrap 95% CI + 多重比較 BH-FDR 校正。

| 對手 | macro-F1 Δ (winner − 對手) | bootstrap 95% CI | McNemar p | BH-FDR 校正後 p | 顯著贏？ |
|------|----------------------------|------------------|-----------|------------------|----------|
| `_TBD_` | `_TBD_` | [`_TBD_`, `_TBD_`] | `_TBD_` | `_TBD_` | `_TBD_` |
| `_TBD_` | `_TBD_` | [`_TBD_`, `_TBD_`] | `_TBD_` | `_TBD_` | `_TBD_` |

**決策鐵則：CI 跨 0（或與對手重疊）≠ 一場勝利。** 只有當 macro-F1 差的 bootstrap CI **不含 0**、且 BH-FDR 校正後 McNemar p < 0.05，才宣稱 winner 顯著優於該對手；否則視為「打平 / 證據不足」。

---

## 5. 校準（calibration）

> 模型給的機率有多可信。`ml/ml/metrics.py`：`expected_calibration_error`（含 adaptive 等量分箱）、`brier_score`、`nll`。Qwen 硬標無機率 → 跳過校準。

| 候選 | ECE ↓ | Brier ↓ | NLL ↓ |
|------|-------|---------|-------|
| winner | `_TBD_` | `_TBD_` | `_TBD_` |
| `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |

> 若 ECE 偏高，考慮溫度校準（`train_classifier.py` 訓練後已做 LBFGS 溫度校準，存於 meta）。

---

## 6. Risk–Coverage / AURC

> 讓模型「沒把握就不答」（abstain）能換到多少準確率。`ml/ml/metrics.py`：`risk_coverage_curve` + AURC、`accuracy_at_coverage`。

| 候選 | AURC ↓ | acc@coverage=1.0 | acc@coverage=0.8 | acc@coverage=0.5 |
|------|--------|-------------------|-------------------|-------------------|
| winner | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |
| `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |

---

## 7. 忠實度指標（僅事件摘要任務）

> 摘要任務專用。對應 `ml/ml/faithfulness.py`：`faithfulness_report`。一般分類任務可略過本節。

| 候選 | faithfulness_score ↑ | mean_entailment ↑ | frac_entailed ↑ | frac_contradicted ↓ | citation_validity ↑ | source_coverage ↑ |
|------|----------------------|-------------------|-----------------|---------------------|---------------------|-------------------|
| baseline | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |
| winner | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |

盲測成對偏好（若有）：

| 對比 | 偏好 winner | 偏好對手 | 平手 | 樣本數 | 二項檢定 p |
|------|-------------|----------|------|--------|------------|
| `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` | `_TBD_` |

---

## 8. 決策

> 一段話寫清楚：採用哪個候選、根據哪條證據、哪些對比「證據不足不算贏」。

```
決策：採用 <候選>。
理由：在 <gold set vN> 上 macro-F1 = _TBD_，對 <對手> 的差 CI = [_TBD_, _TBD_]（不含 0）、
      BH-FDR 校正後 McNemar p = _TBD_ < 0.05，故顯著優於 <對手>。
保留：對 <候選 X> 的差 CI 跨 0，視為打平，不宣稱優勝。
校準：ECE = _TBD_（<可接受 / 需溫度校準>）。
忠實度（如適用）：faithfulness_score _TBD_ ≥ baseline，frac_contradicted _TBD_。
```

寫回 `evaluation_runs` 表（每候選一列）+ MLflow run。
