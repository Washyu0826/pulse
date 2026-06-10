# Offline Evaluation 文獻回顧（Phase 4）

> 為 `scripts/evaluate.py` 奠基：嚴謹比較「英文舊模型 vs 微調中文新模型」在人工 gold set 上的
> 表現（macro-F1、McNemar、bootstrap CI、校準、選擇性預測）。~50 篇 / 4 軸，2026-06-05 整理。
> 與 `docs/research/sentiment-literature.md` 互補（那篇是情緒穩健化；這篇是評測方法學）。
>
> 對應決策：[[chinese-nlp-pivot]]（A/B = Offline Evaluation；非線上 A/B）。

---

## 軸一：顯著性檢定與分類器比較（13）

| 論文 | 對 evaluate.py 的意涵 |
|---|---|
| **Dietterich 1998**, Approximate Statistical Tests (Neural Computation) | 各模型「只跑一次」時，**McNemar 是唯一 Type-I error 可接受的檢定**；別用兩比例 z 檢定比兩個 accuracy。小樣本用精確二項。 |
| **Koehn 2004**, Significance Tests for MT (EMNLP) | **paired bootstrap**：同一組重抽索引上同時評兩模型，取 macro-F1 差的分布。~300 筆即可用。 |
| **Berg-Kirkpatrick 2012** (EMNLP) | bootstrap 與 permutation 大致一致；小增益/小集合時 bootstrap 偏寬鬆 → 邊界情形改信 permutation。 |
| **Riezler & Maxwell 2005** (ACL WS) | approximate randomization 比 bootstrap 更保守 → headline 主張用更嚴 α（0.01）。 |
| **Dror et al. 2018**, Hitchhiker's Guide (ACL) | 依指標型態選檢定：accuracy→McNemar；macro-F1（不可分解）→bootstrap/permutation。 |
| **Søgaard et al. 2014**, What's in a p-value (CoNLL) | 只報 p 不可靠；要報**效果量 + CI**，注意 covariate（長度/主題）。 |
| **Benjamini-Hochberg 1995** (JRSS-B) | 多個 per-class/per-task 檢定用 **BH-FDR q=0.05**，別用 Bonferroni 壓死。 |
| **Dror et al. 2017**, Replicability (TACL) | 兩任務/各 strata 當「多資料集」，報「k/m 條件勝出」而非各自獨立宣稱。 |
| **Reimers & Gurevych 2017**, Score Distributions (EMNLP) | 微調模型非確定性 → **跑 ≥3–5 seeds 報 mean±std**，別憑單一 checkpoint 宣稱贏。 |
| **Sälevä et al. 2025**, Beyond Statistical Significance (AACL) | 同時計**模型(seed)變異 + 資料(bootstrap)變異**；只報 bootstrap CI 會低估不確定性。 |
| **Card et al. 2020**, With Little Power (EMNLP) | 做**檢定力分析**定 gold size；分層保證**每類 ≥30–50 筆**否則 McNemar 格子退化。 |
| **Takahashi et al. 2022**, CI for Micro/Macro-F1 (Appl. Intell.) | macro-F1 是非線性 → 有 delta-method 解析 CI 可與 bootstrap 互相 sanity check。 |
| **Opitz & Burst 2019**, Macro-F1 note | macro-F1 有兩種定義！**固定用「per-class F1 取平均」**（= sklearn macro）並寫明。 |

也參考：CI for F1 四方法比較（arXiv 2309.14621，建議 BCa bootstrap）。

---

## 軸二：信心校準與選擇性預測（14）

| 論文 | 對 evaluate.py 的意涵 |
|---|---|
| **Guo et al. 2017**, Calibration (ICML) | **溫度縮放**在 val 上以 NLL 擬合；不改 top-1，校準要另報。已用於 sentiment.py / train_classifier.py。 |
| **Nixon et al. 2019**, Measuring Calibration (CVPRW) | 固定分箱 ECE 有缺陷 → 用 **adaptive(等量)分箱 + classwise-ECE**（類別不平衡時重要）。 |
| **Roelofs et al. 2022**, Bias in ECE (AISTATS) | 分箱 ECE 是**有偏估計**，小樣本尤甚 → 報 bin 數或用無箱法。 |
| **Błasiok & Nakkiran 2024**, smECE (ICLR) | 核平滑、無 bin 數旋鈕的 **smECE** → 小 gold set 的首選校準純量 + reliability diagram。 |
| **Kull et al. 2019**, Dirichlet Calibration (NeurIPS) | 可修 per-class 偏差，當 T-scaling 的 ablation 對照（classwise-ECE/Brier）。 |
| **Mukhoti et al. 2020**, Focal Loss Calibration (NeurIPS) | 訓練期校準槓桿；shift 下 post-hoc 不夠時改用。 |
| **Desai & Durrett 2020**, Calibration of Pretrained Transformers (EMNLP) | BERT 類**域內校準好、域外退化**；T-scaling 助域內、label smoothing 助域外 → 你的 silver→Threads gold 正是 shift。 |
| **Geifman & El-Yaniv 2019**, SelectiveNet (ICML) | 用 **risk–coverage 曲線**評你的 softmax 門檻棄答（你做的是其 baseline）。 |
| **Ziyin et al. 2019**, Deep Gamblers (NeurIPS) | 學習式棄答；啟發報「明確棄答類 + 其 precision」。 |
| **Traub/Bungert et al. 2024**, Flaws in Selective-Class Eval (NeurIPS) | AURC 有缺陷 → 改報 **AUGRC**（未偵測失誤的平均風險），門檻無關。 |
| **Ovadia et al. 2019**, Trust Your Uncertainty? (NeurIPS) | shift 下**域內擬合的 T 可能變更差** → 校準要分「域內 val」與「Threads gold」分別報。 |
| **Jones et al. 2021**, Selective Class Magnifies Disparities (ICLR) | risk–coverage 要**按類別拆解**，確認棄答沒犧牲少數類。 |
| **Geng et al. 2024**, Survey of Confidence/Calibration in LLMs (NAACL) | NLP 校準該一起報 **ECE+Brier+NLL+AUROC/AURC**。 |
| **Wen et al. 2025**, Survey of Abstention in LLMs (TACL) | 門檻式棄答是受認可的一族；報 coverage + abstain precision/recall。 |

也參考：Selective Conformal Risk Control（用 val 設門檻達目標選擇性風險，gold 上報實際 coverage）。

---

## 軸三：silver 訓練 / noisy gold 的可信度（12）

| 論文 | 對評測可信度的意涵 |
|---|---|
| **Northcutt et al. 2021**, Pervasive Label Errors (NeurIPS D&B) | 測試集約 3.4% 標錯就能**翻轉模型排名** → 用 confident learning 清 gold、人工複審後再報。 |
| **Nahum et al. 2024**, Are LLMs Better than Reported? (EMNLP) | 用 LLM 集成**偵測 gold 標錯**，修正後表現上移；模型「答錯」可能是 gold 錯。 |
| **Pangakis & Wolken 2024**, KD in Automated Annotation (ACL WS) | LLM 標籤訓練的學生**可比人工標籤**，但僅在乾淨人工 gold 上量得到 → gold 不可省。 |
| **Yang 2024 / LLM4Annotation survey 2024** | LLM 標註品質**高度任務/類別相依** → 報 per-class，揭露 Qwen 弱的主觀類。 |
| **Just Put a Human in the Loop? 2025** (ACL Findings) | 標 gold **必須盲於 Qwen 輸出**，否則 gold↔silver 一致性虛高、評測循環論證。 |
| **Zheng et al. 2023**, LLM-as-a-Judge / MT-Bench (NeurIPS) | judge 有 position/verbosity/**self-preference** 偏差；強 judge 與人約 80% 一致。 |
| **Self-Preference 2024 / Justice or Prejudice 2024** | **不可用 Qwen 評自家學生**（自我偏好高估）。 |
| **No Free Labels 2025 / Empirical LLM-judge 2025** | 無人工 grounding 的 judge 不穩 → 只當次要訊號、需人工抽查。 |
| **Angelopoulos et al. 2023**, Prediction-Powered Inference (Science) | 小 gold(校正) + 大量 Qwen 預測(無標) → **更窄且有效的 CI**，即使 Qwen 有偏。 |
| **Gligorić et al. 2024**, Confidence-Driven Inference (NAACL) | 用 Qwen 信心挑「該人工標的點」，省 >25% 標註且 CI 有效。 |
| **Kossen et al. 2021/2022**, Active Testing (ICML/NeurIPS) | 小 gold 別隨機抽；主動挑資訊量高的點，估計精度 ~4×。 |
| **BioNLP 2022**, IAA 非 ML 上限 | κ 是**參考非硬上限**；F1 遠超同一 noisy gold 的 κ 多半是過擬合噪聲。 |

統計註：Raschka 2022（bootstrap test-set CI）；小 N 下 CI 很寬，**落在重疊 CI 內的 2–3 分「贏」不算贏**。

---

## 軸四：MLOps 追蹤、報告標準與中文基準（13）

| 參考 | 對 Pulse 的意涵 |
|---|---|
| **MLflow 2018 / Developments 2020** | 每次離線評測 = 一個 MLflow run；DB `evaluation_runs` 是可查詢的時序鏡像；Model Registry 管 staging→production。 |
| **W&B Artifacts/Registry docs** | **把 gold set 當有版本的 artifact**（alias production/candidate），每次 run 記錄評的是哪版 gold。 |
| **Pineau et al. 2021**, Reproducibility Checklist (JMLR) | run 必記：code commit、gold hash、模型版本、解碼參數(temperature/seed)、指標定義。 |
| **Gundersen et al. 2022**, Sources of Irreproducibility | LLM-as-classifier 的**非確定性是頭號風險** → 評測一律 `temperature=0` 並記錄。 |
| **Mitchell et al. 2019**, Model Cards (FAT*) | Pulse model card 9 節；指標要**按類別 + 按語別**（zh-Hant 原生 vs 英譯）拆解。 |
| **Gebru et al. 2021**, Datasheets / **Bender & Friedman 2018**, Data Statements | 為 gold set 寫 datasheet + data statement（抽樣、標註者、類別平衡、時間窗、語別 zh-TW）。 |
| **Breck et al. 2017**, ML Test Score / **Zinkevich**, Rules of ML | 監控 training/serving skew、壞預測、漂移、模型陳舊；**測 eval harness 本身**（固定答案 fixture）。 |
| **Ribeiro et al. 2020**, CheckList (ACL) | 建行為回歸測試（MFT 明確正負必過；INV 否定/emoji/繁簡不該翻轉）→ 升版 gate。 |
| **CLUE/TNEWS (Xu 2020)** | **主題**公開錨點：報 TNEWS accuracy（簡中，僅轉移參考）。 |
| **ChnSentiCorp / NLPCC** | **情緒**公開錨點：報 macro-F1 + per-class P/R/F1（SOTA ~92–93% F1）。 |
| **TMMLU+ (Tam 2024) / TC-Eval (Hsu 2023) / DRCD** | **繁中/台灣**驗證錨點（證明語別對；CLUE/CMMLU 是簡中只作轉移參考）。 |
| **CMMLU/C-Eval 2023-24** | 僅描述底模一般中文能力，非情緒/主題。 |
| **漂移綜述 2024** | 區分 data drift 與 concept drift；每日跑 → 監控預測分布 + 每週重評 rolling gold。 |

---

## evaluate.py 設計 spec（綜合 10 點）

1. **主指標 = 各任務 macro-F1**（per-class F1 取平均；明寫定義）；輔以 accuracy、weighted-F1、per-class P/R/F1、confusion。
2. **accuracy 顯著性 = paired McNemar 精確二項**（小樣本），記錄 2×2 cells。
3. **macro-F1 顯著性 = paired bootstrap**（差值 CI；邊界情形加 permutation 交叉驗）；CI 用 BCa、≥5000 resamples、處理小類 0-TP 退化。
4. **同時計 seed 變異 + bootstrap 變異**；新模型跑 ≥3 seeds 報 mean±std。
5. **多重比較用 BH-FDR q=0.05**；headline（整體情緒/主題勝出）用 α=0.01。
6. **校準分「域內 val」與「Threads gold」分別報**：smECE（主）+ 15-bin ECE（輔，註明 bin）+ classwise-ECE + Brier + NLL；T 只在 val 擬合，並驗 gold 上是否反而更差。
7. **選擇性預測**：用 softmax-response 畫 risk–coverage，報 **AURC + AUGRC + acc@coverage(100/90/80/70%)**，並**按類別拆解**確認沒犧牲少數類；新舊模型在**相同 coverage** 下比 accuracy。
8. **gold 先清洗**：confident learning 標可疑→人工複審；gold 標註**盲於 Qwen**；報 κ + bootstrap CI 當參考天花板。
9. **可信度護欄**：silver 訓練 → 明標「silver-trained, gold-evaluated」、報 per-class；落在重疊 CI 內不算贏；可選 PPI 收窄 CI；若用 LLM judge 必用**非 Qwen** 模型 + 控偏差 + 人工抽查。
10. **可重現**：每 run 記 code commit、gold 版本/hash、模型版本、`temperature=0`、seed；寫 `evaluation_runs` + MLflow；附 model card 與 gold datasheet。

> 公開基準對外講法：情緒引 **ChnSentiCorp**、主題引 **TNEWS/CLUE** 當錨點，但以 **TMMLU+/TC-Eval** 證明繁中/台灣語別有效；CLUE/CMMLU 為簡中、僅作轉移參考。
