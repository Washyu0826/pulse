# ADR-008：採用 Offline Evaluation 取代 A/B Test 術語

**狀態**：Accepted
**日期**：2026-05-08
**觸發**：Mentor Review 建議 #3

## 背景

v3 計畫書中使用「A/B Test 框架」描述「用 200 筆人工標註資料對比兩個情緒模型 F1」。這在業界精確的術語是錯誤的。

## 業界精確定義

| 術語 | 定義 |
|------|------|
| **Offline Evaluation** | 用標註資料集評估模型，在離線環境 |
| **Shadow Testing** | 新模型跑 production 流量但不影響使用者，只記錄差異 |
| **A/B Testing** | 真實使用者流量分流，看行為差異（CTR、retention） |
| **Canary Deployment** | 新模型先給 1% 流量，觀察後逐步擴大 |

Pulse 做的是「用標註資料集評估」，正確術語是 **Offline Evaluation**。

## 決定

1. 將 v3 的「F12 A/B Test 框架」更名為「**F12 Offline Evaluation 框架**」
2. 文件中所有相關描述更新為精確術語
3. v2 番外篇規劃增加 **Shadow Testing**（production 同跑兩模型、記錄差異供分析）
4. 新增 `evaluation_runs` 表紀錄歷史評估結果

## 評估設計

### Offline Evaluation Pipeline

```
1. 準備
   - Model A: cardiffnlp/twitter-roberta-base-sentiment-latest
   - Model B: cardiffnlp/twitter-xlm-roberta-base-sentiment
   - Ground truth: 200 筆人工標註資料（從 production 抽樣）

2. 執行
   - 從 production 抽 2000 筆樣本（涵蓋多個模型、多種主題）
   - Model A、B 分別推論
   - 跟 ground truth 比對

3. 計算指標
   - F1 (macro / weighted)
   - Precision / Recall (per class: positive / neutral / negative)
   - Cohen's Kappa（標註一致性）
   - Confusion Matrix

4. 統計顯著性
   - McNemar's test（兩模型在同樣資料上的對比）
   - p < 0.05 才視為有意義的差異

5. 紀錄
   - MLflow Run（含參數、指標、artifacts）
   - evaluation_runs 表（含 mlflow_run_id 連結）
```

### 標註流程設計

- 自己標 200 筆（不要找朋友，會稀釋一致性）
- 標 3 類：positive (1) / neutral (0) / negative (-1)
- 隨機抽樣，不要 cherry-pick
- 重複標 20 筆做 inter-rater consistency（不同時間自己標兩次）
- 目標 self-consistency Cohen's Kappa > 0.8

### evaluation_runs 表

```sql
CREATE TABLE evaluation_runs (
    id              BIGSERIAL PRIMARY KEY,
    model_version   VARCHAR(100) NOT NULL,
    evaluation_set  VARCHAR(50),         -- e.g., "200_labels_v1"
    sample_size     INT NOT NULL,
    f1_macro        FLOAT,
    f1_weighted     FLOAT,
    precision_per_class JSONB,
    recall_per_class    JSONB,
    confusion_matrix    JSONB,
    cohen_kappa     FLOAT,
    mcnemar_p_value FLOAT,                -- 對比基準模型的 p value
    baseline_model  VARCHAR(100),
    mlflow_run_id   VARCHAR(100),
    notes           TEXT,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

## v2 番外篇：Shadow Testing 規劃

完成 Pulse v1 後加入 Shadow Testing：

```
Production traffic
    ↓
   Model A (primary, 100% 使用者看到)
    ↓
   Model B (shadow, 同樣輸入推論一次，只記錄)
    ↓
   shadow_results 表
    ↓
   定期分析兩模型在 production 真實資料的差異
```

這個的價值是**用 production 真實分布**做評估，不是 labeled set 的人工分布。

## 對外溝通

履歷可以寫：

```
- Built Offline Evaluation pipeline with 200 hand-labeled
  samples and 2000 production samples
- Achieved F1 improvement from 0.73 → 0.81 by switching
  sentiment model (validated with McNemar's test, p < 0.01)
- Tracked all evaluation runs in MLflow for reproducibility
```

面試也可以講：

> 「我做的是 Offline Evaluation，不是 A/B Test。A/B Test 需要真實使用者流量分流，但情緒模型沒有使用者行為訊號可量，所以用 labeled dataset。如果之後有 production traffic，會升級成 Shadow Testing。」

這段話展示**精確區分業界術語**的能力，比寫「A/B Test」強很多。

## 後果

### 好處

- 術語精確、面試說話有底氣
- 知道 Shadow Testing 是延伸方向
- MLflow + evaluation_runs 表讓所有評估可重現

### 代價

- 第一次接觸的人可能要查「Offline Evaluation 是什麼」（小問題）

## 之後可能要重新考慮的情境

- Pulse 真的有大量使用者，開始 A/B Test UI 設計差異
- 想做 Reinforcement Learning from Human Feedback（RLHF）
