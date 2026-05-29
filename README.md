# Pulse v4.0

> AI 工程師的每日情報秘書 — 每天 5 分鐘掌握 AI 圈、不錯過該知道的、需要查時 30 秒給答案。
>
> **v4.0 採納 Mentor Review**：加 Data Quality Check、改 Offline Evaluation、補架構圖、改用 Apache Airflow。

## 這是什麼

Pulse 從 Reddit 與 HackerNews 抓取 AI 模型相關討論，做情緒分析、主題分群、事件偵測，產出每日快照、決策報告與即時警示。

**核心功能**
- 📅 每日模型快照
- 🔍 自訂查詢（議題 + 時間範圍）
- 🛡️ Data Quality Check（5 層過濾器，v4 新增）
- 📢 發布事件偵測
- 📉 情緒翻轉偵測
- 🧠 LLM 決策報告

## 技術棧（v4 更新）

- **後端**：FastAPI + SQLAlchemy 2.x + Alembic + PostgreSQL
- **排程**：Apache Airflow 2.9+（v4 從 Prefect 改）
- **DQC**：lingua-py + 自訂 5 層過濾器（v4 新增）
- **ML**：Hugging Face Transformers (RoBERTa) + BERTopic + Anthropic API
- **評估**：MLflow（Offline Evaluation，v4 術語校正）
- **前端**：Next.js 14 (App Router) + Server Components + shadcn/ui + Tailwind
- **基礎設施**：Docker Compose + Railway + Prometheus + Grafana
- **CI/CD**：GitHub Actions

## 架構

完整架構圖見 [docs/architecture.md](docs/architecture.md)（含 Mermaid 系統圖、Sequence Diagram、Railway 部署圖、DQC flowchart、Offline Evaluation 流程）。

```
pulse/
├── api/        FastAPI 後端
├── workers/    Airflow DAGs + 爬蟲 + DQC
│   ├── dags/
│   ├── plugins/
│   └── crawlers/
├── ml/         ML 邏輯（情緒、主題、事件、DQC、LLM）
├── web/        Next.js 14
├── docs/
│   ├── Pulse_Project_Plan_v4.docx  ⭐ 完整計畫書
│   ├── architecture.md             ⭐ 系統架構圖
│   ├── TASKS.md                    ⭐ 14 週任務（給 Claude Code）
│   ├── MENTOR_REPLY.md             Mentor 回信草稿
│   └── decisions/                  9 個 ADR
└── scripts/
```

## 快速啟動

### 前置需求

- Docker Desktop（含 WSL Integration）
- Node.js 20+
- Python 3.11+（推薦 [uv](https://github.com/astral-sh/uv)）
- Reddit API key
- Anthropic API key

### 啟動

```bash
# 1. clone
git clone <this-repo> pulse && cd pulse

# 2. 設定環境變數
cp .env.example .env
# 編輯 .env 填入 API keys

# 3. 啟動所有服務（業務 DB + Airflow + Airflow metadata DB）
docker compose up -d

# 4. 等 Airflow init 完成（首次約 30 秒）
docker compose logs -f airflow-init

# 5. 安裝後端依賴 + 跑 migration
cd api && uv sync && uv run alembic upgrade head

# 6. 啟動 API
cd api && uv run uvicorn api.main:app --reload

# 7. 啟動前端（另一個 terminal）
cd web && npm install && npm run dev
```

訪問：
- 前端：http://localhost:3000
- API 文件：http://localhost:8000/docs
- Airflow UI：http://localhost:8080（帳號 admin / 密碼 admin，dev only）

## 開發路線

14 週逐週任務見 [docs/TASKS.md](docs/TASKS.md)。

完整專案計畫見 [docs/Pulse_Project_Plan_v4.docx](docs/Pulse_Project_Plan_v4.docx)。

技術選型理由見 [docs/decisions/](docs/decisions/)。

## v3 → v4 變更摘要

| 變更 | 來源 |
|------|------|
| 新增 F14 Data Quality Check（5 層過濾器） | Mentor Review #1 |
| 補上系統架構圖（Mermaid + Sequence） | Mentor Review #2 |
| A/B Test → Offline Evaluation（術語校正） | Mentor Review #3 |
| Prefect → Apache Airflow | Mentor Review #4 |
| 時程 12 週 → 14 週 | 新功能 + Airflow 學習 |
| 預算 $26 → $31/月 | Airflow 多服務 |

完整變更紀錄見 PRD docx 附錄 A。

## 作者

冼冠宇 · Xchange · Data Project
