# Mentor 回信草稿（v4 更新）

> 本檔案是給冠宇參考的回信草稿，可依關係親疏調整語氣。

---

## 短版（LinkedIn / 簡短訊息用）

> 老師您好，
>
> 非常感謝您給的四個建議，每一條都打到要害。我已經全部納入 v4.0 計畫書：
>
> 1. ✅ Data Quality Check：新增 F14 功能（5 層過濾器 + dq_runs 觀測表）
> 2. ✅ 系統架構圖：補上 Mermaid 系統架構圖 + 資料流 Sequence Diagram
> 3. ✅ Offline Evaluation：F12 更名 + 細化評估設計（含 McNemar's test）
> 4. ✅ Apache Airflow：全盤取代 Prefect，時程調整為 14 週
>
> 完整 ADR (007-009) 記錄了每個決策的權衡。再次感謝您的指導！
>
> 冠宇

---

## 完整版（Email / 認真討論用）

```
Dear [Mentor name],

非常感謝您撥冗 review 我的 Pulse 計畫書，並提供四個具體建議。
我認真思考過每一條，全部納入 v4.0 版本，以下逐一回報採納情況。

【建議 #1：Data Quality Check】✅ 完整採納

新增為 F14 核心功能，設計 5 層過濾器：
- Layer 1：基本格式（長度、刪除標記、純 URL / emoji）
- Layer 2：語言檢測（用 lingua-py，比 langdetect 短文更準）
- Layer 3：垃圾偵測（bot 帳號 pattern、24h 重複內容、連結農場）
- Layer 4：相關性（關鍵字必須在正文，不能只在 URL / code block）
- Layer 5：情緒可靠性（反諷標記、全大寫）

每筆 post 計算 quality_score (0-100)，三檔處理：
- >= 60：納入情緒彙總、事件偵測
- 30-59：分析但不彙總（debug 用，保留復原緩衝）
- < 30：丟棄

新增 dq_runs 表記錄每次 DQC 執行摘要，供 Grafana 監控。
預估效益：情緒模型 F1 從 0.73 提升到 0.81+，事件偵測 false
positive 降低 30%。

【建議 #2：系統架構圖】✅ 完整採納

新增 docs/architecture.md，含五張 Mermaid 圖：
1. 高層次系統架構（資料來源 → Airflow → DB → API → 前端）
2. 資料流 Sequence Diagram（單篇貼文生命週期）
3. Railway 部署架構
4. DQC 內部流程 flowchart
5. Offline Evaluation 流程

所有圖用 Mermaid 語法，於 GitHub README 自動 render，
評審 / 面試官打開就看得到。

【建議 #3：A/B Test → Offline Evaluation】✅ 完整採納

完全同意，這是我的術語精確度不足。已將：
- F12 從「A/B Test 框架」改名為「Offline Evaluation 框架」
- 所有相關描述更新

額外延伸：v2 番外篇規劃 Shadow Testing — production 同跑兩
模型、記錄差異供分析。新增 evaluation_runs 表追蹤所有評估歷
史，含 McNemar's test 統計顯著性檢定（p < 0.05）與 Cohen's
Kappa（標註一致性 > 0.8）。

【建議 #4：Apache Airflow】✅ 完整採納

雖然這對個人專案是較大的工程投入，我評估後決定全盤改用 Airflow，
理由：
1. 中大型企業主流，履歷在 LinkedIn 招聘配對量多 5-10 倍
2. 「會做選擇」< 「會 Airflow」這個產業現實
3. 真的學一次受用 5 年（Airflow 2.x 穩定）

時程調整為 14 週（原 12 週）：
- 新增 Week 3 給 DQC 開發
- 新增 Week 5 給 Airflow 學習 + 環境設定
- 後續 Week 順移

預算微調：$26 → $31/月（Railway 多服務需 Pro plan）。

技術設計：
- Executor：LocalExecutor（個人專案規模適用）
- Metadata DB：獨立 Postgres，不與業務 DB 混用
- 7 個 DAG：crawl_reddit, crawl_hackernews, data_quality,
  ml_pipeline, event_detection, daily_snapshot, weekly_report

完整 ADR 紀錄（給未來自己跟其他工程師看）：

- ADR-007: 從 Prefect 改用 Airflow
- ADR-008: Offline Evaluation Strategy
- ADR-009: Data Quality Check 設計

這四個建議從根本提升了專案的紮實度。我尤其感謝您點出
「Offline Evaluation」這個術語精確度的問題 — 這種細節在書本上
很難學到，是業界資深工程師才會點到的。

開發進度我每月會發 update 給您，期待 14 週後跟您展示 demo！

冠宇
```

---

## 重點訊息（如果只能講三句）

1. **四個建議全部納入 v4.0**，不是只挑容易的做
2. **時程調整為 14 週**（mentor 該知道你願意為品質拉長時程，不是死守 deadline）
3. **新增 3 份 ADR 記錄決策**（mentor 會驚豔，這是資深工程師才有的習慣）

---

## 關於 Airflow 取捨的補充說明（如 mentor 追問）

如果 mentor 追問「為什麼選擇全盤改用 Airflow 而不是折衷方案」，可以這樣回：

> 折衷方案（v1 Prefect、v2 Airflow blog）我認真考慮過，
> 但有個現實：v2 番外篇實際發生機率 < 50%，因為 v1 完成
> 後我就要開始投履歷，blog 的優先順序會被排到後面。
> 與其做半套，不如一次到位。
>
> 而且您點出來時我意識到：選 Prefect 當時是因為「個人專案
> 規模 Prefect 更貼」這個技術判斷，但這個判斷只在「不考慮
> 履歷」前提下成立。考慮履歷的話，Airflow 學一週換 5 年職
> 涯加分，CP 值更高。

這個回答展示**重新評估自己的判斷**的能力，比死撐 v3 決策強。
