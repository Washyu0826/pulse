# 情緒分析文獻survey（30+ 篇）與實作對應

> 為 Pulse 的情緒分析模組（`ml/ml/sentiment.py`）做的文獻研究。
> 兩條主線：(A) 情緒分類的穩健化、(B) 時序情緒動態 / 翻轉偵測。
> 每篇標 ✅ 已實作 / 🔭 未來工作。實作細節見 `ml/ml/sentiment.py` 的對應註解。

問題背景：模型用 `cardiffnlp/twitter-roberta-base-sentiment-latest`（**Twitter** 上訓練、3 類），
但 Pulse 的文本是**技術論壇英文**（HN/Dev.to/Lobsters）→ 領域不匹配 + 過度自信 + 天真聚合。

---

## A. 情緒分類的穩健化

### A1. 模型本體（TweetEval 家族）
1. **TweetEval** · Barbieri et al. (2020) · Findings of EMNLP · <https://aclanthology.org/2020.findings-emnlp.148/> — 我們情緒 head 的訓練 benchmark；neutral 是「中性或混合」。🔭（理解 label 語意）
2. **TimeLMs** · Loureiro et al. (2022) · ACL Demos · <https://arxiv.org/abs/2202.03829> — `-latest` checkpoint 來源；凍結於 2021 → 新模型名（GPT-5）未見、register 不匹配。🔭
3. **SemEval-2017 Task 4** · Rosenthal et al. (2017) · <https://aclanthology.org/S17-2088/> — pos/neu/neg 標註定義來源。🔭

### A2. 領域不匹配 / 校準
4. **Calibration of Pre-trained Transformers** · Desai & Durrett (2020) · EMNLP · <https://aclanthology.org/2020.emnlp-main.21/> — RoBERTa 跨域會過度自信，溫度縮放可救。✅（`temperature` 參數）
5. **On Calibration of Modern Neural Networks** · Guo et al. (2017) · ICML · <https://arxiv.org/abs/1706.04599> — 溫度縮放（單一純量除 logits）。✅（`logits / temperature`，預設 1.0，待標註資料擬合）
6. **VADER** · Hutto & Gilbert (2014) · ICWSM · <https://ojs.aaai.org/index.php/ICWSM/article/view/14550> — 規則+詞典；可當低信心時的第二意見。🔭（詞典融合，避免加依賴暫緩）
7. **Adversarial & Domain-Aware BERT for Cross-Domain SA** · Du et al. (2020) · ACL · <https://aclanthology.org/2020.acl-main.370/> — 目標域 MLM 後訓練。🔭（需訓練，未來）

### A3. 信心 / 棄答
8. **Selective Prediction (Art of Abstention)** · Xin et al. (2021) · ACL · <https://aclanthology.org/2021.acl-long.84/> — 校準信心 + 門檻 → 棄答。✅（`confident` 旗標、`min_confidence`/`min_margin` 棄答帶）
9. **SelectiveNet** · Geifman & El-Yaniv (2019) · ICML · <https://arxiv.org/pdf/1901.09192> — coverage–risk 拒答。✅（三區決策：高信心才算 pos/neg）

### A4. 反諷 / 反語
10. **SemEval-2018 Task 3: Irony** · Van Hee et al. (2018) · <https://aclanthology.org/S18-1005/> — `twitter-roberta-base-irony` 的訓練資料。🔭（可加 irony gate）
11. **Automatic Sarcasm Detection: A Survey** · Joshi et al. (2017) · ACM CSUR · <https://arxiv.org/pdf/1602.03426> — 反諷線索（/s、scare quotes、誇飾）。✅（`flag_sarcasm` 規則旗標）
12. **Sarcasm Detection Survey** (2024) · <https://arxiv.org/html/2412.00425v1> — 論壇反諷重度依賴 `/s` 標記。✅（同上）

### A5. 群體聚合（取代天真投票）
13. **Dawid–Skene** (1979) · JRSS-C · <https://www.jstor.org/stable/2346806> — 依可靠度加權聚合 > 多數決。✅（信心加權 soft index）
14. **Fast Dawid–Skene** · Sinha et al. (2018) · <https://arxiv.org/pdf/1803.02781> — 快速投票聚合 + 處理 neutral 過多。✅（同上 + 降權 neutral）
15. **Aggregating Soft Labels under Distribution Shift** (2024) · PLOS ONE · <https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0323064> — 用 soft 機率聚合比 argmax 穩健。✅（用 `p(pos)-p(neg)` soft）

### A6. Aspect-based（未來）
16. **ABSA Survey** · Zhang et al. (2022) · <https://arxiv.org/pdf/2006.04611> — 面向級情緒（讚價格、罵穩定）。🔭
17. **Instruct-DeBERTa / Generative ABSA** (2024) · <https://arxiv.org/pdf/2408.13202> — 生成式 (aspect, polarity)。🔭

---

## B. 時序情緒動態 / 翻轉偵測

### B1. 變點偵測
18. **Bayesian Online Changepoint Detection** · Adams & MacKay (2007) · <https://arxiv.org/abs/0710.3742> — 線上 run-length 後驗，每日「翻轉機率」。🔭
19. **PELT** · Killick et al. (2012) · JASA · <https://arxiv.org/abs/1101.1438> — O(n) 精確分段（回顧式）。🔭
20. **CUSUM / EWMA control charts** · Romano et al. (2022) 等 · <https://arxiv.org/abs/2210.17353> — 累積偏差、偵測小而持續的位移。🔭（線上告警的下一步）

### B2. 社群情緒動態
21. **Real-Time Sentiment Change Detection of Twitter Streams** · Tasoulis et al. (2018) · <https://arxiv.org/abs/1804.00482> — 處理後即丟、只留 running stats。🔭（架構範式）
22. **Detecting Abnormal Feedback via Temporal Sentiment Aggregation** (2026) · <https://arxiv.org/abs/2604.00020> — 窗口聚合 + 控制圖偵測向下位移＝口碑異常。🔭（幾乎就是「口碑翻轉」）
23. **In the mood: collective sentiments on Twitter** · Garcia et al. (2016) · R. Soc. Open Sci. · <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC4929909/> — 翻轉應相對「各自基準」而非全域 0。🔭（per-model 基準）

### B3. 統計顯著性
24. **Two-proportion Z-test** · <https://en.wikipedia.org/wiki/Two-proportion_Z-test> — 比較兩期負評率是否顯著不同。✅（`detect_flip` 用 z 檢定取代固定門檻）
25. **Wilson score interval** · Wilson (1927); Brown, Cai & DasGupta (2001) · Statistical Science · <https://www.ncbi.nlm.nih.gov/pmc/articles/PMC2706447/> — 小樣本比例 CI；非重疊才算翻轉。🔭（CI 顯示，已用收縮替代）

### B4. 量+情緒的聯合異常
26. **Bursty and Hierarchical Structure in Streams** · Kleinberg (2002) · KDD · <https://www.cs.cornell.edu/home/kleinber/bhs.pdf> — burst 偵測的理論基礎。🔭（對應現有 z-score spike）
27. **Good and bad events: event detection + sentiment** (2020) · SNAM · <https://link.springer.com/article/10.1007/s13278-020-00681-4> — 先偵測量 burst，再貼情緒＝好/壞事件。🔭（spike + 負情緒 = 口碑危機）
28. **Real-Time Sentiment-Based Anomaly Detection (RSAD)** · Guha et al. (2015) · Springer LNCS · <https://link.springer.com/content/pdf/10.1007/978-3-319-18356-5_17.pdf> — 對**負評流**跑 PEWMA + MAD。🔭（現有 MAD 偵測器套在負評計數上，幾乎零新碼）

### B5. 平滑
29. **PEWMA / EWMA baselines** — 指數加權平滑 + 降權異常點。🔭（每日指數平滑趨勢）
30. **Empirical Bayes / Beta-Binomial shrinkage** · Brown et al. (2001) 等 · <https://en.wikipedia.org/wiki/Empirical_Bayes_method> — 小樣本比例朝先驗收縮。✅（`summarize` 的 `n/(n+shrink)` 收縮）

### B6. 極化 / 爭議
31. **Measuring Political Polarization (Twitter, Venezuela)** · Morales et al. (2015) · Chaos · <https://arxiv.org/abs/1505.04095> — 極化指數＝質量落在兩極多少。✅（`polarization` = 2·min(pos,neg) 比例）
32. **Quantifying Controversy on Social Media** · Garimella et al. (2018) · ACM TSC · <https://dl.acm.org/doi/10.1145/3140565> — 爭議為一級可追蹤指標。✅（分歧度作為獨立訊號）

---

## 已實作技術總結（→ `ml/ml/sentiment.py`）

| 技術 | 論文 | 實作 |
|------|------|------|
| 溫度縮放（機制） | Guo 2017, Desai 2020 | `temperature` 參數，`logits/T` |
| 信心棄答帶 | Xin 2021, Geifman 2019 | `confident` 旗標、min_confidence/min_margin |
| 信心加權 soft 聚合 | Dawid-Skene 1979, PLOS 2024 | `summarize` 用 `Σw·(p_pos-p_neg)/Σw` |
| 小樣本收縮 | Brown 2001（Beta-Binomial）| `index *= n/(n+shrink)` |
| 兩比例 z 檢定判翻轉 | Two-proportion z-test | `detect_flip` 的 z/p_value，顯著才算 |
| 極化/分歧度 | Morales 2015, Garimella 2018 | `polarization` 欄位 |
| 反諷標記 | Joshi 2017, Van Hee 2018 | `flag_sarcasm()` |
| label 驗證守衛 | （穩健性）| `__init__` 檢查標籤為 pos/neu/neg |

**未來工作（🔭）**：溫度的實際擬合（需標註 ~300 篇論壇文）、irony gate、CUSUM/BOCPD 線上翻轉、
對負評流跑 MAD（RSAD）做「量+情緒」聯合的口碑危機事件、ABSA 面向級情緒。
