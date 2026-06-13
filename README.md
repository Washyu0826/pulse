# Pulse

> 我從零自建的端到端中文 AI 情報管線：把多來源的 AI 討論（以台灣 Threads 繁中在地訊號為差異化核心），每天爬取、過濾、分類、**忠實摘要**成可查詢的情報，並自動產出電子報與 Threads 草稿——全程地端模型、零雲端 API。

這是一個 **資料 / ML 工程的求職作品集**，同時也是我自己每天真的會打開的產品（過了 N=1 自用測試）。差異化不在「內容」（內容上永遠贏不過 TLDR AI、LMSYS Arena 這些巨量對手），而在 **這整條管線都是我自己做的**：多源爬蟲（含 Selenium 繞登入牆）→ 跨源去重 + 資料品質檢核 → 自訓中文分類模型 → 事件忠實摘要 → 離線評測 → 分發。

**資料底氣：已建約 6 萬篇 AI 語料庫。** DB 現有 ~59.7k 篇多源貼文——HackerNews ~52k、Dev.to ~6.4k（英文量體，餵下游 ML / 去重 / 分類）、**Threads ~1k（台灣繁中，差異化來源，Selenium + cookie）**、PTT ~330（繁中，Selenium）。英文量體靠 `scripts/bulk_backfill.py`（HN Algolia 逐月切窗繞單查詢上限）回填；繁中在地訊號靠 Threads 爬蟲與 `scripts/crawl_ptt.py`（真瀏覽器）。

---

## 這是什麼

- **多源語料、繁中為差異化核心**。語料以英文量體（HackerNews / Dev.to，餵 ML 與去重訓練量）為底，差異化在 **Threads 繁中台灣在地討論**——它同時是差異化資料來源 **與** 分發管道（台灣是 Threads 全球第 1 大市場，台灣的 AI 工具 / 提示詞 / 變現 / 風險討論幾乎都在這裡，是英文競品完全沒覆蓋的在地訊號）；PTT 繁中技術板再補一層在地語料。
- **地端 LLM 優先**：翻譯、蒸餾、摘要走本機 Ollama Qwen2.5；電子報封面走本機 Stable Diffusion。無 Anthropic / OpenAI 雲端 API、零推論成本、可 24/7 跑。
- **技術核心 = 事件忠實摘要（Faithful Event Summarizer，非 RAG）**：把同一事件的多篇貼文聚成叢集，抽關鍵句，用 LoRA 微調的繁中小模型改寫成「帶行內來源引用、且經 NLI 忠實度查核」的事件摘要。我做過很多 RAG，這次刻意做不一樣的——自訓生成模型 + 忠實度專門化。
- **深 NLP + 離線評測**：建人工 gold set（含 κ 標註者一致性）、用 Qwen 蒸餾 silver labels、微調 `hfl/chinese-macbert-base` 取代原本的英文 zero-shot；模型選型走 **Offline Evaluation**（非線上 A/B），用 macro-F1 + McNemar + paired-bootstrap CI + BH-FDR 多重比較校正，外加校準（ECE / Brier）與 risk–coverage（AURC）。

### 一句話定位

> 我自架的端到端中文 AI 情報管線——把台灣 Threads 的 AI 討論，過濾、分類、**忠實摘要**成可查詢的個人情報，再自動分發成電子報與 Threads 草稿。重點是這條管線（含自訓模型與離線評測）全是我自己做的。

---

## 架構總覽

```
多源 AI 貼文（~59.7k：HN ~52k · Dev.to ~6.4k · Threads ~1k 繁中 · PTT ~330 繁中）
   │  workers/crawlers（廣義 AI 門檻 + 繁體過濾）· bulk_backfill.py（HN 逐月切窗）· crawl_ptt.py（Selenium）
   ▼
跨源近似去重（SimHash + Jaccard）＋ 資料品質檢核 DQC（多層啟發式評分）
   │  ml/ml/dedup.py · ml/ml/data_quality.py
   ▼
主題分類（5 類 + 其他，mDeBERTa zero-shot）＋ 情緒（RoBERTa, GPU）＋ 熱詞 ＋ 英文貼地端翻譯
   │  ml/ml/theme.py · sentiment.py · keywords.py · translate.py
   ▼
事件忠實摘要（技術核心）
   │  BGE-M3 嵌入 → HDBSCAN 聚事件 → MMR 抽關鍵句
   │  → LoRA Qwen2.5-1.5B 帶引用改寫 → mDeBERTa-NLI 忠實度查核
   │  ml/ml/event_cluster.py · faithfulness.py
   ▼
分發：每日電子報（地端摘要 + matplotlib 圖表 + SD 封面 + Gmail SMTP）
       ＋（路線圖）自動鑄 Threads 草稿
   │  ml/ml/newsletter.py · charts.py · scripts/send_newsletter.py
   │
   └─ 橫向：Offline Evaluation 模型選型 bake-off
          gold set → 多候選 macro-F1 排名 → McNemar + bootstrap CI + BH-FDR
          ml/ml/metrics.py · scripts/evaluate.py · annotate.py · distill_labels.py · train_classifier.py
```

完整 Mermaid 系統圖、事件摘要管線圖與離線評測流程見 [docs/architecture.md](docs/architecture.md)。
技術核心的深入個案研究見 **[docs/case-study-faithful-event-summarizer.md](docs/case-study-faithful-event-summarizer.md)**。

---

## 主題分類（5 類 + 其他）

依「AI 資訊需求」研究訂出的 taxonomy（見 [ml/ml/theme.py](ml/ml/theme.py)）：

| 主題 | 範圍 |
|------|------|
| 新工具 | 新的 AI 工具 / app / 產品 / 功能發表 |
| 模型動態 | 模型比較 / 評測 / 排名 / 價格 / 能力更新（「哪個最好」） |
| 使用方法 | 提示技巧 / 教學 / 工作流 / use case（台灣旗艦需求） |
| 風險限制 | 實務限制 / 失敗 / 幻覺 / 不該用的情況 |
| 倫理法規 | 倫理 / 法規 / 政策 / 隱私 |
| 其他 | 低信心 fallback |

主題彼此不互斥，分類器會輸出 top-2（`label` + `secondary`），對應「一篇可同時是新工具 + 使用方法」的真實情況。

---

## 技術棧（實況）

- **後端**：FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL
- **排程**：Apache Airflow DAGs（本機每日刷新另有 `scripts/daily_refresh.ps1` + Windows 排程）
- **ML（地端優先）**：
  - 主題：mDeBERTa-v3 多語 zero-shot（`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`）→ 將被微調的 `hfl/chinese-macbert-base` 取代
  - 蒸餾 / 摘要 / 翻譯：本機 Ollama **Qwen2.5**
  - 事件摘要：BGE-M3 嵌入 + HDBSCAN + MMR + LoRA Qwen2.5-1.5B + mDeBERTa-NLI 忠實度查核
  - 評測：純 stdlib 手刻指標（`ml/ml/metrics.py`）+ 選配 MLflow 追蹤
- **資料來源**：多源爬蟲（HN Algolia / Dev.to API + Threads / PTT 走 Selenium 真瀏覽器繞登入牆與反爬）；`scripts/bulk_backfill.py` 以 HN Algolia **逐月切窗**繞單查詢 ~1000 筆上限，灌出 ~6 萬篇量體
- **資料品質**：跨源近似去重（`ml/ml/dedup.py`，SimHash + token Jaccard + union-find）+ 多層啟發式 DQC（`ml/ml/data_quality.py`）
- **前端**：Next.js 14（App Router + Server Components）
- **電子報**：matplotlib 圖表 + 本機 Stable Diffusion 封面 + Gmail SMTP
- **基礎設施**：Docker Compose
- **設計原則**：ML 邏輯寫成**純函式**（重依賴函式內延遲載入），核心邏輯不裝 torch / transformers 也能單元測試

---

## 功能清單

- Threads 爬蟲：廣義 AI 相關門檻（`is_ai_related`）+ 繁體過濾（`looks_simplified`）擋簡體中國內容
- 多層資料品質檢核（DQC）：扣分制 quality_score（垃圾/廣告/SEO、模型相關性、實質長度）
- 主題分類（5 類 + 其他，top-2 輸出）+ 情緒 + 中文熱詞（jieba + OpenCC）
- 英文貼文地端翻譯（Qwen2.5），feed 中英並列
- 事件忠實摘要管線（聚類 / 抽句 / 帶引用改寫 / NLI 忠實度查核）
- 每日電子報（地端摘要 + 圖表 + SD 封面 + Gmail 寄送）
- 互動式人工標註器 + Offline Evaluation 模型選型 bake-off
- Next.js 前端 feed / 看板

---

## 目前進度 / 路線圖

誠實標示已完成 vs 進行中。**資料底氣已備：DB 已有約 6 萬篇（~59.7k）多源 AI 語料，HN/Dev.to 量體已跑完跨源去重、情緒（RoBERTa, GPU）與主題（mDeBERTa zero-shot）。** 事件摘要四階段管線模組（含端到端膠合）、評測基礎設施、電子報都已建好，純邏輯皆有完整單元測試；剩重模型整合（BGE-M3 / Qwen / mDeBERTa）、gold set 標註與 LoRA 微調受限於資料與算力，尚在進行（LoRA 模型尚未訓練）。

> **已知問題（地端 LLM）**：PyTorch GPU 推論（情緒 / 分類）正常；但 Ollama 內附的 CUDA build 目前會 crash，導致需要 Ollama 的「真實模式」翻譯與摘要暫時受阻——管線純邏輯與假模型路徑不受影響。

| 階段 | 內容 | 狀態 |
|------|------|------|
| 來源 / 語料庫 | 多源爬蟲（HN / Dev.to + Threads / PTT Selenium）、`bulk_backfill.py` 逐月切窗、跨源去重、DQC、熱詞、翻譯 | ✅ 已建，**DB ~59.7k 篇**（HN ~52k / Dev.to ~6.4k / Threads ~1k 繁中 / PTT ~330 繁中） |
| 分類 | 主題 5 類 zero-shot（mDeBERTa）、情緒（RoBERTa, GPU）、前端 feed | ✅ 已建並跑過 HN/Dev.to 量體；**誠實發現：主題分布嚴重偏向「新工具」**——這正是下一步要監督式微調 `chinese-macbert-base` 的動機（前端 5 類顯示與 backfill 待補） |
| 評測基建 | `metrics.py`（F1 / McNemar / bootstrap CI / ECE / Brier / AURC / BH-FDR）、`evaluate.py` N-候選 bake-off、`evaluation_runs` 表、標註器 | ✅ 已建（純函式皆有測試；McNemar/ECE/Brier/BH-FDR 已加已知數值回歸測試鎖定） |
| 電子報 | 純函式組版 + 圖表 + SD 封面 + SMTP 編排 | ✅ 已建 |
| 可觀測性 / 可靠性 | Prometheus 自訂指標 + Grafana 面板、`alerts.yml` 告警（DAG 失敗 / scheduler 心跳 / 資料新鮮度）、監控服務 healthcheck、`check_dataflow.py` 盤中 `--lag-only`、`daily_refresh.ps1` 失敗彙總並 exit 1、Threads 爬蟲 fallback selector + 零結果告警 | ✅ 已建（Sprint 4；Alertmanager 路由與 Airflow 排程 `--lag-only` 仍 🔜） |
| 訓練可重現 | 訓練腳本 checkpoint / load_best / 中斷續跑、torch/numpy/random 三處 seed、可讀 OOM / 中斷錯誤 | ✅ 已建（Sprint 4；**LoRA 實際訓練尚未跑**，見下方 Step 3） |
| 前端測試 | Vitest 單元測試（lib 工具、URL 參數生成、SVG 邊界、localStorage、API 錯誤在地化），首次前端測試覆蓋 | ✅ 已建（Sprint 4，7 檔 45 測試） |
| 事件摘要管線 | 四階段純模組——聚類 + 抽句（`event_cluster.py`）、兩段式帶引用生成（`summarize.py`）、句級 NLI 忠實度查核（`faithfulness.py`），加端到端膠合 `event_pipeline.run_pipeline` | ✅ 已建，純邏輯**完整單元測試**（`test_event_cluster` 36 / `test_summarize` 25 / `test_faithfulness` 35，注入假 embedder/LLM/NLI）；僅重模型路徑待跑 |
| 事件摘要 Step 1 | 接真實 BGE-M3 + 本機 Qwen + mDeBERTa 跑第一批真摘要，上電子報「今日事件」 | 🔜 進行中（管線就緒，待接重模型） |
| 深 NLP Step 2 | 人工標 200–500 筆 gold（κ > 0.8）+ Qwen 蒸餾 silver + NLI 過濾 | 🔜 待資料 |
| Step 3 | 微調 `chinese-macbert-base`（分類）/ LoRA 微調 Qwen2.5-1.5B（摘要，模型尚未訓練） | 🔜 待資料 + 算力 |
| Step 4 | bake-off：分類用 macro-F1、摘要用忠實度 + 盲測偏好 + 速度 | 🔜 待 Step 3 |
| Step 5 | 整合上線：電子報「今日事件」+ 自動鑄 Threads 草稿 | 🔜 規劃中 |

技術選型理由見 [docs/decisions/](docs/decisions/)（含 ADR-008 為何用 Offline Evaluation 而非 A/B Test）。

---

## 如何執行

> 重 ML 依賴（torch / transformers / FlagEmbedding / hdbscan / peft / diffusers / matplotlib）跑在系統 Python（GPU），需先 `pip install`。純函式模組與測試不需要這些套件。

```bash
# 1. 環境變數
cp .env.example .env   # 填 SMTP / DB 等設定

# 2. 啟動 DB（Docker Compose）
docker compose up -d

# 3. API：跑 migration + 啟動
cd api && uv sync && uv run alembic upgrade head
uv run uvicorn api.main:app --reload   # 本機慣用 8010 埠

# 4. 前端（另一個 terminal）
cd web && npm install && npm run dev
```

常用工作流（在專案根目錄、用系統 Python）：

```bash
# 人工標註 gold set（互動式，中文優先）
python scripts/annotate.py --target 200 --zh

# 用 Qwen 蒸餾 silver labels
python scripts/distill_labels.py

# 微調中文分類器
python scripts/train_classifier.py --task theme --gold data/gold/gold.jsonl \
    --silver data/silver/silver_theme.jsonl --out models/theme-macbert --mlflow

# Offline Evaluation bake-off（多候選排名 + 統計顯著性）
python scripts/evaluate.py --task theme --gold data/gold/gold.jsonl \
    --models models/theme-macbert --with-qwen --mlflow

# 每日電子報（--dry-run 只存 HTML 預覽，不寄信）
python scripts/send_newsletter.py --dry-run

# 每日全流程刷新（Windows 排程）
pwsh scripts/daily_refresh.ps1
```

---

## 文件導覽

- [docs/architecture.md](docs/architecture.md) — 系統架構、事件摘要管線、離線評測流程（Mermaid）
- [docs/case-study-faithful-event-summarizer.md](docs/case-study-faithful-event-summarizer.md) — 技術核心個案研究 ⭐
- [docs/pipeline-composition.md](docs/pipeline-composition.md) — 事件摘要四模組怎麼組（含零依賴可跑範例 + 範例 fixture dry-run）
- [docs/evaluation-report-template.md](docs/evaluation-report-template.md) — bake-off 評測報告範本
- [docs/annotation-guidelines.md](docs/annotation-guidelines.md) · [docs/annotation-codebook-100.md](docs/annotation-codebook-100.md) — 標註 codebook
- [docs/research/offline-evaluation-literature.md](docs/research/offline-evaluation-literature.md) — 離線評測文獻回顧
- [docs/decisions/](docs/decisions/) — 架構決策紀錄（ADR）

---

## 作者

冼冠宇 · Xchange · Data Project
