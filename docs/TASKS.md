# Pulse 開發任務清單 v4.0（給 Claude Code 用）

> v4 更新：採納 Mentor Review、改用 Airflow、新增 DQC、時程改 14 週。
> 每週一段，你直接複製貼到 Claude Code 對話裡。

## 整體技術約束（每次都要遵守）

**必讀**：開始前請讀 `docs/decisions/` 的所有 ADR（特別是 007-009 v4 新增的）。

### 通用原則

- **Monorepo 結構**
- **SQLAlchemy 2.x async style**：`select(...)`，不要用 `session.query(...)`
- **driver 用 asyncpg**：`postgresql+asyncpg://`
- **Models 跟 Schemas 分開**：`api/models/` vs `api/schemas/`
- **永遠用 Alembic 改 schema**
- **Next.js Server Components 為主**
- **fetch 用 `next: { revalidate: ... }`**
- **環境變數透過 `api/config.py` 的 `settings`**

### v4 新增的約束

- **Airflow DAG 用 TaskFlow API**（不要寫舊式 PythonOperator）
- **DQC 必須在情緒分析前跑**（看 ADR-009）
- **Offline Evaluation 不寫成 "A/B Test"**（看 ADR-008）
- **DAG 失敗策略**：retries=3, retry_delay=exponential backoff

---

## Phase 1：基礎建設（Week 1-4）

### Week 1：Reddit API + Models + Next.js 雛形

**目標**：能從 Reddit 抓 100 篇貼文存進 Postgres，Next.js 首頁顯示假資料卡片。

**前置**
- 申請 Reddit / Anthropic API key
- `docker compose up -d` 啟動 Postgres
- `cd api && uv sync`

**任務**

1. 建立 `api/models/models.py`（Models 主表）
2. 建立 `api/models/posts.py`（Posts 表，**v4 加 quality_score, quality_flags 欄位**）
3. Seed 6 個預設模型
4. 建立 `workers/crawlers/reddit.py`（用 asyncpraw）
5. 手動測試腳本 `scripts/test_crawl.py`
6. Next.js 雛形

**驗收條件**
- [ ] Postgres 啟動、migration 跑完
- [ ] 能抓 r/ClaudeAI 50 篇存進 DB
- [ ] http://localhost:3000 看到 6 張卡片
- [ ] http://localhost:8000/docs 看到 OpenAPI

---

### Week 2：HackerNews + 多模型抓取 + API endpoints

**目標**：6 模型每日抓 1000+ 篇，API 能查到資料給前端。

**任務**

1. `workers/crawlers/hackernews.py`（Algolia API）
2. `workers/crawlers/crawl_all.py`（6 模型 × 8 subreddit + HN）
3. API endpoints：`/api/models`、`/api/models/{slug}`、`/api/models/{slug}/posts`
4. 前端 Server Component 串 `/api/models`

**驗收條件**
- [ ] 手動跑 crawl_all → DB 有 6 模型各幾百篇
- [ ] `curl localhost:8000/api/models` 回 JSON
- [ ] 前端顯示真實 post count

---

### Week 3：Data Quality Check (v4 新增 ⭐)

**目標**：實作 5 層 DQC pipeline，確保 ML pipeline 不被雜訊污染。

**任務**

1. 加 `lingua-py` 依賴到 `api/pyproject.toml` 跟 `workers/pyproject.toml`
2. 建 `ml/data_quality.py`：
   - `DataQualityChecker` class
   - `check(post: Post) -> QualityResult`
   - 實作 5 層過濾器（規則見 ADR-009）
3. 建 `api/models/dq_run.py`（dq_runs 表）+ alembic migration
4. 建 `workers/dqc/processor.py`：批次處理未檢核的 posts
5. 整合到 crawl flow：抓完馬上跑 DQC
6. 寫測試：覆蓋每個 layer 的 edge case
7. 加 API `GET /api/dq/recent-runs` 看歷史
8. 前端首頁加「今日資料品質」小卡片

**驗收條件**
- [ ] 跑 1000 篇真實 Reddit 資料 → 看到 quality_score 分布合理
- [ ] dq_runs 表有紀錄
- [ ] bot 偵測 spot check 10 個 username → 抓對 9+
- [ ] 反諷標記抓得到 (`/s` 結尾的貼文)
- [ ] 單筆 DQC < 50ms
- [ ] pytest 全綠

---

### Week 4：情緒分析 + FastAPI

**目標**：每篇 DQC 過關的貼文都有情緒分數，前端顯示真實情緒。

**任務**

1. 建立 `ml/sentiment.py`（SentimentService class）
2. FastAPI lifespan 載入模型
3. 建 `api/models/sentiment.py`（sentiments 表）
4. API endpoint `POST /api/analyze`
5. 批次腳本 `scripts/backfill_sentiments.py`
   - **只跑 quality_score >= 30 的 posts**（v4 變更）
6. API 端模型加情緒資料
7. 前端顯示真實情緒（紅綠燈）

**驗收條件**
- [ ] FastAPI 啟動 log 看到模型載入
- [ ] `POST /api/analyze` 可用
- [ ] DB sentiments 表有資料（只含高品質貼文）
- [ ] 前端「Claude +68 ↑」這類數字正確

---

## Phase 2：自動化 + 核心功能（Week 5-8）

### Week 5：Airflow 學習 + 環境設定 (v4 新增 ⭐)

**目標**：Docker Compose 加 Airflow services，第一個 DAG 跑通。

**前置學習（先看 1-2 天）**
- Airflow 2.x TaskFlow API 寫法
- LocalExecutor vs CeleryExecutor 差異
- DAG / Task / XCom 基本概念
- 推薦教材：Astronomer 官方教程、Marc Lamberti 的 YouTube 系列

**任務**

1. 更新 `docker-compose.yml`：
   - 加 `airflow-postgres`（metadata DB）
   - 加 `airflow-init`（一次性 migration）
   - 加 `airflow-webserver` + `airflow-scheduler`
   - 用 `airflow-common` YAML anchor 共用設定
2. `workers/` 結構調整：
   - 新增 `workers/dags/`（放 DAG 檔案）
   - 新增 `workers/plugins/`（自訂 operator / hook）
   - 更新 `pyproject.toml`：移除 prefect，加 `apache-airflow>=2.9.0`
3. 寫第一個 DAG：`workers/dags/hello_dag.py`（每分鐘印 hello）
4. 確認 Airflow Webserver UI 可訪問（http://localhost:8080）
5. 設定 Airflow Connection：DB（業務 Postgres）、Slack（webhook）
6. 寫 ADR-007 補完細節

**驗收條件**
- [ ] `docker compose up -d` 起所有服務（含 Airflow）
- [ ] Airflow UI 看得到 hello_dag 並正常執行
- [ ] DAG 能讀寫業務 Postgres（用 Airflow Connection）
- [ ] Slack 通知能成功送出

---

### Week 6：Airflow DAG 完整化

**目標**：6+ DAGs 上線，系統 24/7 自己跑。

**任務**

1. `workers/dags/crawl_reddit_dag.py`：每 15 分鐘
2. `workers/dags/crawl_hackernews_dag.py`：每 15 分鐘
3. `workers/dags/data_quality_dag.py`：依賴 crawl 完成
4. `workers/dags/ml_pipeline_dag.py`：依賴 DQC 完成
5. `workers/dags/aggregate_hourly_dag.py`：每小時
6. DAG 失敗 → Slack 通知（用 `on_failure_callback`）
7. 用 Airflow Datasets / ExternalTaskSensor 處理依賴

**驗收條件**
- [ ] Airflow UI 看到 5+ DAG 都在跑
- [ ] 連續 24 小時 DB posts 持續增加
- [ ] 故意讓 DAG 失敗 → Slack 收到通知
- [ ] DQC processing 量正常（每 15 分鐘 200-500 筆）

---

### Week 7：事件偵測 + 每日快照

**目標**：兩類事件偵測上線 + 每日快照功能完整。

**任務**

1. `ml/event_detection.py`：`detect_launch`、`detect_sentiment_flip`
2. `api/models/event.py`（events 表）
3. `workers/dags/event_detection_dag.py`：每 15 分鐘
4. `api/models/snapshot.py`（sentiment_daily, daily_snapshots 表）
5. `workers/dags/daily_snapshot_dag.py`：每天 01:00
   - 計算 6 模型表現、Top 貼文、熱門主題
   - LLM 產出一句總評
6. API endpoints：`/api/events`、`/api/daily`、`/api/daily/latest`
7. 前端：事件流首頁 + `/daily` 頁面

**驗收條件**
- [ ] 跑歷史回放：能偵測到 GPT-4o 發布、Gemini 圖像爭議
- [ ] events 表有資料
- [ ] daily_snapshots 每天有新資料
- [ ] 首頁看到事件卡片、`/daily` 頁面完整

---

### Week 8：自訂查詢 + LLM 報告

**目標**：F3 + F4 完整可用。

**任務**

1. `ml/llm_report.py`：呼叫 Claude Haiku
2. `api/models/report_cache.py`（llm_reports 表）
3. `POST /api/decide` endpoint
4. 前端 `/decide` 頁面（Client Component）
5. `ml/topic_modeling.py`：BERTopic
6. `workers/dags/topic_daily_dag.py`：每天跑

**驗收條件**
- [ ] `POST /api/decide` 回完整 JSON
- [ ] 同樣 query 第二次回 cached 版本
- [ ] `/decide` 頁面能用
- [ ] LLM 月用量 < $20

---

## Phase 3：上線 + 監控（Week 9-11）

### Week 9：Railway 部署

**任務**

1. 註冊 Railway，創 Pulse project
2. 加 PostgreSQL（業務）+ PostgreSQL（Airflow metadata）
3. 部署 5 個 service：
   - API
   - Web
   - Airflow Webserver
   - Airflow Scheduler
   - （可選）Airflow Worker（用 LocalExecutor 不需要）
4. 環境變數設定
5. 跑 production migration
6. 觀察 5 天

**驗收條件**
- [ ] 公開網址可訪問
- [ ] Airflow UI 也公開（或 basic auth 保護）
- [ ] DB 持續有新資料
- [ ] 連續 5 天穩定

---

### Week 10：CI/CD + Docker 強化

**任務**

1. 完整化 `.github/workflows/ci.yml`
2. `.github/workflows/deploy.yml`：push main 自動部署
3. pre-commit hooks（含 detect-secrets）
4. Docker multi-stage build 優化

**驗收條件**
- [ ] PR 自動跑 CI
- [ ] CI 失敗 PR 不能 merge
- [ ] push main 自動部署
- [ ] Docker image < 1.5GB

---

### Week 11：Prometheus + Grafana 監控

**任務**

1. FastAPI 加 prometheus_client
2. Airflow 啟用 statsd metrics
3. docker-compose 加 Prometheus + Grafana
4. **四個 Grafana dashboards**（v4 多一個 DQC）：
   - API metrics
   - Airflow DAG metrics
   - Business metrics
   - **DQC metrics（v4 新增）**：每日高品質比例、flag 分布
5. Alert rules → Slack

**驗收條件**
- [ ] Grafana 4 個 dashboard 都有資料
- [ ] 故意讓 API 報錯 → alert 觸發
- [ ] DQC dashboard 看得到 bot 偵測率

---

## Phase 4：打磨 + 發表（Week 12-14）

### Week 12：Offline Evaluation + UI 打磨 + 週報

**目標**：MLflow 有資料、UI 完整、週報能寄出。

**任務**

1. **Offline Evaluation 完整化（v4 強調）**：
   - MLflow 整合
   - 加第二個情緒模型對比
   - 自己標 200 筆
   - 算 F1、Cohen's Kappa、McNemar's test
   - 寫進 evaluation_runs 表
2. UI 打磨（動畫、loading、暗色切換、mobile）
3. `workers/dags/weekly_report_dag.py`：每週一 08:00 寄 email

**驗收條件**
- [ ] MLflow UI 看到 2 模型對比
- [ ] evaluation_runs 表有完整紀錄
- [ ] McNemar p < 0.05 證明差異
- [ ] UI 截圖可上履歷封面
- [ ] 寄出一份週報 email

---

### Week 13：文件 + 3 篇 blog

**任務**

1. README 大改版（含 Mermaid 架構圖）
2. `docs/architecture.md`（已完成 v4 規劃，補實作截圖）
3. Blog 1：「我如何用 14 週搭建 AI 圈情報秘書」
4. Blog 2：「Data Quality Check：從 0.73 → 0.81 的 5 層過濾器」
5. Blog 3：「Airflow vs Prefect：同一個 pipeline 兩種實作的心得」
6. 發 Medium / Hashnode / 個人網站

---

### Week 14：Demo 影片 + 收尾

**任務**

1. 錄 5 分鐘 demo 影片
2. 發 LinkedIn / Twitter
3. 整理履歷敘述（v4 量化指標）：
   - 「DQC 提升情緒模型 F1 從 0.73 → 0.81」
   - 「偵測 X 個 AI 模型事件，Precision 85%+」
   - 「用 Airflow + MLflow 建構完整 MLOps 工作流」
4. 練面試講稿（30s / 3min / 15min）

**驗收條件**
- [ ] 影片上 YouTube
- [ ] LinkedIn 貼文 50+ 互動
- [ ] 履歷 5 個量化指標寫好

---

## 給 Claude Code 的精準提示模板（v4）

```
我在做 Pulse 專案 v4（個人版 + Mentor Review 採納版）。

技術棧：
- 後端: FastAPI + SQLAlchemy 2.x async + Alembic + PostgreSQL
- 前端: Next.js 14 App Router (Server Components 為主)
- 排程: Apache Airflow 2.9+ (TaskFlow API)
- ML: HF transformers + BERTopic + Anthropic API
- DQC: lingua-py + 自訂 5 層過濾器

請先讀 docs/decisions/ 所有 ADR（特別是 007 Airflow、008
Offline Eval、009 DQC），再讀 docs/architecture.md 看架構圖，
然後讀 docs/TASKS.md 找對應週次的任務。

本週要做：[Week N - 主題]

開始前確認你會遵守：
- SQLAlchemy 2.x async style
- Airflow DAG 用 TaskFlow API (@dag, @task)，不要寫舊式 PythonOperator
- DQC 必須在情緒分析前跑
- 術語：Offline Evaluation（不是 A/B Test）
- 環境變數透過 settings 物件

請先列出本週要做的所有檔案異動，等我確認後再動手。
```

---

## 卡關時的求助對象

- **架構決策** → docs/decisions/ ADR
- **Airflow 寫法** → Astronomer docs、Marc Lamberti YouTube
- **DQC 規則** → docs/decisions/009-data-quality-check.md
- **要不要砍功能** → docs/PROJECT_PLAN.md 的「砍功能優先順序」
