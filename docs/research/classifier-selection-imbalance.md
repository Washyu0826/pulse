# 中文分類器：base model 選型 × 嚴重類別不平衡 × silver 標籤可信度

> 為 `scripts/train_classifier.py`（微調）與 `scripts/evaluate.py`（bake-off）奠基。
> 任務：繁中短文兩分類器 —— **theme**（6 類：新工具/模型動態/使用方法/風險限制/倫理法規/其他）
> 與 **sentiment**（negative/neutral/positive）—— 取代現行弱設定（英文 cardiffnlp/twitter-roberta
> 情緒 + MoritzLaurer/mDeBERTa-v3 zero-shot 主題）。
> 硬體：單張 RTX 4060 Laptop 8GB VRAM（~100M BERT 全量微調可行，大模型不可行）。
> 資料現況：~51k silver（zero-shot/RoBERTa teacher），**嚴重偏斜**（theme：新工具 66%、其他 23%、
> 使用方法 4%、模型動態/風險限制/倫理法規 各 <0.6% → 各只有幾十筆）；**gold 極少/尚未建立**。
> 2026-06-10 整理。標 ⚠️ 者為不確定主張。

---

## TL;DR（可直接落地）

1. **Base model**：主力選 **`hfl/chinese-lert-base`** 與 **`hfl/chinese-macbert-base`** 兩個下去 bake-off；
   多語對照組放 **`microsoft/mdeberta-v3-base`**。三者皆 ~100M（mDeBERTa ~278M 但 backbone 仍可在 8GB
   以 batch 8 + grad-accum 微調）。**全部資料先過 OpenCC `t2s` 正規化成簡體再丟給 tokenizer**（見 §1.3）。
2. **不平衡**：teacher 端先**合併/降級**極稀有 theme 類（§2.4），訓練端用 **class-weighted CrossEntropy
   （`sqrt`-inverse-freq 上限封頂）** 當預設，focal loss 當對照；搭配 **per-class decision threshold 調整**
   與 **LLM 合成增強只補稀有類**。focal 不是萬靈丹，常需調 γ 且不穩（§2.1）。
3. **Gold set**：目標 **每類 ≥50 筆（理想 80–100）**，theme 至少 6×50 = **300+ 筆、且 class-balanced**
   （非自然分佈）；sentiment 3×80 ≈ **240 筆**。先用 cleanlab 在 silver 上挑「最可能標錯」的優先送人工。

---

## 1. Base model 選型（2026）

### 1.1 候選比較

| 模型 | 參數 | 預訓練語言 | 8GB 可行性 | 對本專案的判斷 |
|---|---|---|---|---|
| **hfl/chinese-macbert-base** | ~102M | 簡體為主（wiki+EXT） | 全量微調輕鬆（batch 16–32） | 現行 baseline。MacBERT 的「MLM as correction」訓練讓它在多數中文分類穩定，是安全選擇。 |
| **hfl/chinese-lert-base** | ~102M | 簡體為主 | 同上 | **LERT（Cui 2022）注入語言學特徵（POS/NER/依存），在 CLUE 分類任務通常小幅優於 RoBERTa-wwm/MacBERT**；短文主題分類值得當主力候選。⚠️ 增益視任務在 0.5–1.5 macro-F1 量級。 |
| **hfl/chinese-roberta-wwm-ext** | ~102M | 簡體為主 | 同上 | 經典強 baseline，與 MacBERT 互有勝負；若 LERT/MacBERT 兩席已滿，這個可省略或當第三方驗證。 |
| **Langboat/mengzi-bert-base** | ~103M | 簡體 | 同上 | 預訓練語料較小、偏通用；無證據在繁中短文超過 hfl 系，列為備援。 |
| **microsoft/mdeberta-v3-base** | ~278M（embedding 大） | 多語（含中文，CC100） | batch 8 + grad-accum 2、max_len 256 → 8GB 可訓 ⚠️（需開 fp16/gradient-checkpointing） | DeBERTa-v3 的 disentangled attention 在 XNLI/分類常勝 XLM-R；**作為多語對照很有價值**，且它正是你現在 zero-shot 用的同家族 → 公平對比「微調 > zero-shot」。 |
| **xlm-roberta-base** | ~270M | 多語 | 同 mDeBERTa | 多語 baseline，但 base 版分類普遍被 mDeBERTa-v3 壓過，可不放。 |
| **Alibaba-NLP/gte-multilingual-base** | ~305M（含 RoPE/GLU，8192 ctx） | 多語（70+，含中文） | 可微調但偏 retrieval/embedding 取向 | 強在檢索/embedding；當 sequence-classification head 微調**沒有證據優於專用中文 encoder**，且體積/工程成本高 → 本專案不建議當分類主力。 |
| **Chinese ModernBERT**（2025, arXiv 2510.12285） | ~377M | 簡體（1.2T tokens, CCI3/CCI4） | 8GB 偏吃緊 ⚠️ | 新架構（RoPE+local/global attn, 8192 ctx），CLUE 上與 RoBERTa-wwm-large 互有勝負、**未全面超越**；且**作者尚未釋出權重**（"upon camera-ready"）、未提繁中支援 → 觀望，勿納本輪 bake-off。 |

> Benchmark 依據：CLUE 是中文理解標準榜（含 TNEWS 15 類短新聞、IFLYTEK 長文分類）；hfl 系（BERT-wwm/RoBERTa-wwm/MacBERT/LERT）皆在其技術報告與 CLUE 上系統性報告，base 級彼此差距通常在 1 個百分點上下，**沒有一個壓倒性贏家 → 因此用 bake-off + 顯著性檢定（你 `evaluate.py` 已具備）來定案，而非空談**。

### 1.2 排名建議（挑 2–3 個進 `evaluate.py` bake-off）

1. **hfl/chinese-lert-base**（語言學增強，短文主題分類首選試）
2. **hfl/chinese-macbert-base**（現行、最穩，當對照基準）
3. **microsoft/mdeberta-v3-base**（多語 + 與舊 zero-shot 同家族，驗證「微調是否真贏 zero-shot」）

`train_classifier.py` 已支援 `--base-model`，直接三個各訓一份輸出到不同目錄，再
`python scripts/evaluate.py --task theme --gold ... --models models/theme-lert models/theme-macbert models/theme-mdeberta`
即得 macro-F1 排名 + McNemar + bootstrap CI。**先每模型跑 3 個 seed 報 mean±std**（Reimers & Gurevych 2017，已在 offline-evaluation-literature.md 列為要求），避免單 checkpoint 誤判贏家。

### 1.3 繁中 vs 簡體（關鍵考量，務必處理）

- **絕大多數中文 encoder（hfl 全系、mengzi、ChineseModernBERT）以簡體語料為主預訓練**；繁中字與簡體字僅約 30% 共形，直接餵繁中會踩到大量 OOV/罕見 token，表現掉。
  - 來源：*TMMLU+: An Improved Traditional Chinese Evaluation Suite*（arXiv 2403.01858）—— 同參數級簡體模型可比繁中模型強 ≥19%；繁簡僅約 30% 共享 vocab。
- **建議：所有輸入文字在 tokenize 前一律用 OpenCC `t2s`（繁→簡）正規化**，讓繁中對齊預訓練分佈。這是 NLP 圈處理繁中常見手法（TMMLU+ 等多篇用 OpenCC 在繁簡間轉換）。
  - 落地：在 `train_classifier.py` 的 `_to_ds` 與 `evaluate.py` 的 `_predict_finetuned`、`_load_gold` 之前，對 `text` 統一過一層 `opencc.OpenCC('t2s').convert(text)`；**訓練、評估、線上推論三邊必須一致**（否則 train/serve skew）。⚠️ 注意：個別繁→簡多對一（如「臺/台」「裡/里」）會丟少量資訊，但對分類任務影響極小，淨效益為正。
  - 顯示層（feed、電子報）仍用原始繁中，只有「進模型那一刻」轉簡。
- **替代路線**：CKIP Lab（中研院）的 `ckiplab/bert-base-chinese`、`ckiplab/albert-base-chinese` 是**繁中原生**預訓練，理論上免轉簡。可當第四候選做 sanity check ⚠️（CKIP 多為 token-level 任務 NER/WS/POS 釋出，分類證據較少；用 `BertTokenizerFast`）。建議**先驗證「hfl+OpenCC」這條主線**，CKIP 當對照而非主力。
- mDeBERTa-v3/XLM-R 為多語、含繁中 token，理論上免轉簡；但為了公平比較，建議**也餵簡體**（統一 pipeline），或單獨測「繁中原樣 vs 轉簡」兩版看差異。

---

## 2. 嚴重類別不平衡策略（66% vs 0.5%）

現況 theme：新工具 66% / 其他 23% / 使用方法 4% / 模型動態·風險限制·倫理法規 各 <0.6%（各幾十筆）。
這是**極端長尾 + 稀有類絕對量過小**雙重問題，須「資料層 + 損失層 + 決策層」三管齊下。

### 2.1 損失函數：class-weighted CE 當預設，focal 當對照

- **預設用 class-weighted CrossEntropy**：權重 `w_c = (N / (K · n_c))` 或更穩的 **`sqrt` 反頻率**（`w_c ∝ 1/sqrt(n_c)`）並**封頂**（如 clip 到 [0.5, 10]），避免 <0.6% 類權重爆衝導致訓練震盪。
  - 證據：多份 2024 研究指出 **class-weighted CE 在嚴重不平衡下結果最平衡、跨 seed 變異低、且免額外調參**，比 focal 更穩健可部署（如 2024 漏洞偵測研究：weighted-CE 取得最平衡 F1 且低變異；focal 雖可調出高分但對設定敏感、不穩）。
- **focal loss（Lin 2017, arXiv 1708.02002）當對照**：`FL = -α(1-p)^γ log(p)`，down-weight 易分樣本、聚焦難例。**γ=2、α=class-weight** 為常用起點。對「難負例多」場景強，但**對極稀有類常需調 γ 且不穩** → 不當預設。
- macro-F1 導向：你的 `compute_metrics` 已回報 macro-F1。建議 `TrainingArguments` 加
  `metric_for_best_model="f1_macro"`、`load_best_model_at_end=True`、`save_strategy="epoch"`，
  讓選 checkpoint 對齊稀有類（現行 `save_strategy="no"` 只存最後一個 epoch，會偏多數類）。

**對 `train_classifier.py` 的具體改動**：用自訂 `Trainer.compute_loss` 注入 weighted/focal loss（`nn.CrossEntropyLoss(weight=w)`），權重由 train 集 label 計數算出。新增 `--loss {ce,weighted,focal}` 與 `--focal-gamma 2.0`、`--weight-cap 10.0` 旗標。

### 2.2 取樣

- **稀有類過取樣（oversampling）優於對多數類大幅 undersample**（後者丟掉新工具/其他的大量真實訊號）。
  - 實作：`WeightedRandomSampler`（per-sample weight = class weight），讓每 batch 稀有類露臉。
  - ⚠️ 純複製過取樣易過擬合稀有類 → **務必搭配 §2.3 增強**（讓過取樣的是「變體」而非「複本」）。
- 多數類**輕度** undersample（如新工具從 66% 降到 ~40%）可加速且不傷太多，但別激進。

### 2.3 資料增強（只補稀有類，這是稀有類 <50 筆時的關鍵手段）

- **LLM 合成生成（首選，且你有地端 Qwen）**：用地端 Qwen 對每個稀有類，給定 few-shot 真例 + 類別定義（對齊 `annotation-guidelines.md`），**改寫/生成新貼文**（AugGPT 式 rephrase / LLM2LLM 式對誤判樣本再生成）。
  - 證據：多份 ACL 2024 工作顯示 **LLM 生成資料能一致提升分類、有效緩解偏斜**（如 *Bridging the Data Gap*, EDM 2025；ACL 2024 LLM-augmentation survey）。
  - 把每個 <0.6% 類補到 **每類 ~200–500 筆合成**，並**標記來源（synthetic）**，評估時可做「含/不含合成」消融。
- **Back-translation**：繁中→英→繁中（或經日/韓）產生語意保留的變體；2024 研究報多語 intent 分類 F1 +12%，對非正式/低資源短語特別有效。地端可用你已有的翻譯模型。
- **EDA（Wei & Zou 2019）**：同義替換/隨機插入/交換/刪除。中文以**詞級**操作（先斷詞）較安全；對小資料有效但增益有限，當廉價補充。
- ⚠️ 注意分佈漂移：合成資料**只進 train，gold/val 永遠是真實人工標**，否則評估失真。

### 2.4 何時該合併/降級類別（強烈建議先做）

當某類**真實樣本 <50** 且短期無法靠人工/增強補足時，**勉強保留會讓 macro-F1 被一個學不動的類拖垮、且該類預測不可信**。建議：

- **theme 分階段**：第一版把 **模型動態 / 風險限制 / 倫理法規（各 <0.6%）合併為「其他」或先不單獨輸出**，先做穩 4 類（新工具 / 使用方法 / 其他 [含三稀有] / ⟶ 視 sentiment 一致性）。
  - 待靠 §2.3 合成 + 持續人工標把稀有類各養到 ≥100 真例後，再「升級」拆出來。
  - 這也對齊 Card et al. 2020（檢定力）：每類 <30–50 筆時 McNemar 格子退化、F1 CI 過寬，根本無法可信比較。
- 文件化：在 `meta.json` 記錄當前 label 集與「哪些類被合併/凍結」，evaluate 報告註明。

### 2.5 決策層：per-class threshold 調整

argmax 在不平衡下偏多數類。訓練後**在 val（gold）上對每類掃 decision threshold** 最大化 macro-F1（或對稀有類設較低 threshold 提 recall）。
- 你已有溫度校準（Guo 2017）產生可信機率 → 在校準後機率上調 threshold 最自然。
- 落地：在 `evaluate.py`/推論層加一層 per-class threshold（存進 `meta.json`），多分類可用「one-vs-rest threshold + 退而 argmax」或直接報「threshold 調整後 macro-F1」當另一欄。⚠️ threshold 必須在 val 上調、test/gold 上只套用，否則過擬合。

### 2.6 建議超參數起點（theme，~100M base）

```
loss = weighted CE（sqrt-inverse-freq, cap=10）   # focal γ=2 當對照
sampler = WeightedRandomSampler（過取樣稀有類）
epochs = 5–8（小資料 + 稀有類需多看幾輪；配 early-stop on f1_macro）
lr = 2e-5（hfl 系）/ 1e-5（mDeBERTa-v3，較敏感）
batch = 16（hfl）/ 8 + grad_accum 2（mDeBERTa）；fp16=True
max_length = 256（短社交文足夠；省 VRAM）
warmup_ratio = 0.1, weight_decay = 0.01
metric_for_best_model = f1_macro, load_best_model_at_end = True
seed ∈ {41,42,43} 各跑一次報 mean±std
```

---

## 3. Silver 標籤可信度（在偏斜 zero-shot teacher 上訓練的循環風險）

### 3.1 風險本質

silver 來自 zero-shot/RoBERTa teacher，**student 學的是 teacher 的偏誤**（新工具 66% 正是 teacher 的先驗），這是**循環/confirmation bias**。文獻共識：

- **teacher 在 noisy-label 下會把「壞知識」傳給 student**，純 logit-matching 並非最佳（*Knowledge Distillation with Noisy Labels for NLU*, arXiv 2109.10147）。teacher 仍有用，但需配抗噪手段。
- **Confident Learning / cleanlab（Northcutt 2021）**：用模型自身的 out-of-sample 機率，估計類別轉移矩陣、找出「最可能標錯」的 silver 樣本 → **可移除/修正/降權**這些噪點再訓練。

### 3.2 具體做法

1. **先清 silver**：在 silver 上做 k-fold 訓練得 out-of-sample 機率 → 跑 **cleanlab `find_label_issues`** → 把高度可疑（尤其稀有類被 teacher 亂塞的）剔除或降權。⚠️ 但稀有類本就少，刪太兇會見骨 → 對稀有類偏保守，優先靠人工複核。
2. **gold 永遠不進 train**（你 `train_classifier.py` 已是此設計：gold=val、silver=train），維持評估獨立。
3. **別只信 silver 的 val**：現行「無 gold 時用 silver 切 val」會**樂觀偏誤**（你程式已印警告）—— 正式選型**必須**用 gold（`evaluate.py` 已強制 gold ≥10 才跑，建議提高門檻）。
4. ⚠️ 不確定：是否值得做 student→teacher 的迭代自訓（用 student 重標 silver）。長尾下**易放大偏誤**，除非每輪都用 gold 把關 + cleanlab 清洗，否則不建議。

### 3.3 需要多少 gold？要不要 class-balanced？

- **可信評估的 gold 量**：F1 標準誤 `SE(F1) ≈ √(F1(1-F1)/n_class)`（per-class，n 為該類 support）。要讓**每類 F1 的 95% CI 半寬 ≤ ~0.1**，需 **每類 ≥ ~50 筆**（n=50、F1=0.7 時半寬 ≈ 0.13；n=80 → ≈ 0.10；n=100 → ≈ 0.09）。
  - 來源：test set 需大到能以 ≥95% 信心下結論；`SE(F1)≈√(F1(1-F1)/n)`（多篇臨床/NLP 評估）。
  - Card et al. 2020（已在你 offline-evaluation-literature.md）：**分層保證每類 ≥30–50 筆**，否則 McNemar 格子退化、檢定力不足。
- **要 class-balanced gold（關鍵）**：自然分佈下，稀有類在隨機抽樣的 gold 裡可能 0–2 筆 → 其 per-class F1 完全不可信，也撐不起 macro-F1 評估。**評估集應刻意分層過取樣稀有類，趨近每類等量**。
  - 具體建議：
    - **theme gold**：每類 **50（最低）→ 80–100（理想）**，6 類 → **300–600 筆 class-balanced**。
    - **sentiment gold**：每類 **80**，3 類 → **~240 筆**（neutral 通常多、negative 少，也要刻意補 negative）。
  - ⚠️ class-balanced gold 算的是 **per-class F1 與 macro-F1**（這正是你的主指標）；若要報「實際線上分佈下的 accuracy/weighted-F1」，需另留一份**自然分佈 gold**（或用已知 class prior 重加權 macro 結果）。兩份用途不同，別混。
- **怎麼挑要標的**：別純隨機。用 §3.1 的 model 機率做 **主動學習式取樣**——優先送人工：(a) 稀有類的高信心 silver（驗 teacher 對不對）、(b) 低信心/接近決策邊界樣本、(c) cleanlab 旗標的可疑樣本。能用最少人工標出最有資訊量的 gold。

---

## 4. 落地清單（對應檔案）

| 改哪裡 | 做什麼 |
|---|---|
| `train_classifier.py` | 加 OpenCC `t2s` 正規化（tokenize 前）；自訂 `compute_loss` 支援 `--loss {ce,weighted,focal}`、`--focal-gamma`、`--weight-cap`；`WeightedRandomSampler`；`metric_for_best_model="f1_macro"` + `load_best_model_at_end`；`--base-model` 輪訓 lert/macbert/mdeberta；fp16。 |
| `evaluate.py` | 推論前同樣過 OpenCC（與訓練一致）；加 per-class threshold（在 val 調、gold 套用）；每模型多 seed。 |
| `distill.py` / 新增增強腳本 | 用地端 Qwen 對稀有類做合成增強（rephrase + 標 source=synthetic），只進 train。 |
| 新增清洗步驟 | cleanlab `find_label_issues` 清 silver（稀有類保守）。 |
| label 集 | theme 第一版先合併三個 <0.6% 稀有類；`meta.json` 記錄凍結/合併狀態。 |
| gold 標註 | 目標 class-balanced：theme 每類 ≥50（理想 80–100），sentiment 每類 ~80；主動學習式挑樣。 |

---

## 參考來源（含網址）

- Cui et al., *Pre-Training with Whole Word Masking for Chinese BERT*（BERT-wwm/RoBERTa-wwm/MacBERT）— <https://arxiv.org/pdf/1906.08101>；IEEE/ACM TASLP 版 <https://dl.acm.org/doi/abs/10.1109/taslp.2021.3124365>
- ymcui/Chinese-BERT-wwm（hfl 系模型卡與用法；明示「繁中資料建議用 BERT/BERT-wwm，ERNIE vocab 幾無繁中」）— <https://github.com/ymcui/Chinese-BERT-wwm>
- *Chinese ModernBERT with Whole-Word Masking*（2025，377M，權重未釋出，CLUE 與 RoBERTa-wwm 互有勝負）— <https://arxiv.org/html/2510.12285v1>
- *TMMLU+: An Improved Traditional Chinese Evaluation Suite for Foundation Models*（繁簡僅 ~30% 共形；同級簡體模型強 ≥19%；OpenCC 轉換）— <https://arxiv.org/html/2403.01858v3>
- Alibaba-NLP/gte-multilingual-base（mGTE，多語 encoder，retrieval 取向）— <https://huggingface.co/Alibaba-NLP/gte-multilingual-base>
- CKIP Transformers（中研院繁中原生 BERT/ALBERT）— <https://github.com/ckiplab/ckip-transformers> ；模型卡 <https://huggingface.co/ckiplab/bert-base-chinese>
- Lin et al., *Focal Loss for Dense Object Detection* — <https://arxiv.org/pdf/1708.02002>
- 2024 漏洞偵測比較（weighted-CE 最平衡、focal 對設定敏感不穩）— <https://arxiv.org/pdf/2507.16540>
- Wei & Zou, *EDA: Easy Data Augmentation*（同義替換/插入/交換/刪除）— 概念見綜述
- *Bridging the Data Gap: Using LLMs to Augment Datasets for Text Classification*（EDM 2025）— <https://educationaldatamining.org/EDM2025/proceedings/2025.EDM.long-papers.54/index.html>
- *Large Language Model Data Augmentation for Text-Pair Classification*（ICCPR 2024）— <https://dl.acm.org/doi/10.1145/3704323.3704362>
- 低資源語言文字增強 + 預訓練模型（back-translation/EDA 對小資料有效）— <https://pmc.ncbi.nlm.nih.gov/articles/PMC11041965/>
- Northcutt et al., *Confident Learning / cleanlab*（找標籤錯誤）— <https://l7.curtisnorthcutt.com/confident-learning> ；MIT Data-Centric AI <https://dcai.csail.mit.edu/2024/label-errors/>
- *Knowledge Distillation with Noisy Labels for NLU*（teacher 傳壞知識、logit-matching 非最佳）— <https://arxiv.org/pdf/2109.10147>
- Card et al. 2020, *With Little Power…*（檢定力與每類 ≥30–50 筆）— 見 offline-evaluation-literature.md 軸一
- F1 標準誤與 test set 大小（`SE(F1)≈√(F1(1-F1)/n)`）— 多篇評估方法學（見 §3.3）

> 與既有文獻互補：本篇是「選型 + 不平衡 + 標籤可信度」的訓練面決策；
> `offline-evaluation-literature.md` 是「如何嚴謹比較選出的模型」的評測面方法學。兩篇配合使用。
