# Pulse Workers (v4 — Apache Airflow)

Apache Airflow DAGs，負責：
- 從 Reddit / HackerNews 抓資料
- 跑 DQC（v4 新增）
- 跑情緒分析 + 主題分群
- 產出每日快照
- 偵測事件
- 寄週報

## 開發

```bash
# 啟動 Airflow（在 repo root）
docker compose up -d

# 開 Airflow UI
open http://localhost:8080
# 帳號: admin / 密碼: admin（dev only）

# 安裝本機開發依賴（給 IDE / linter 用）
uv sync
```

## 架構

```
workers/
├── dags/             # Airflow DAGs（檔名 = DAG ID）
│   ├── crawl_reddit_dag.py
│   ├── crawl_hackernews_dag.py
│   ├── data_quality_dag.py       # v4 新增
│   ├── ml_pipeline_dag.py
│   ├── event_detection_dag.py
│   ├── daily_snapshot_dag.py
│   └── weekly_report_dag.py
├── plugins/          # 自訂 Operator / Hook
│   └── pulse_hooks.py
├── crawlers/         # 純爬蟲邏輯（被 DAG 引用）
│   ├── reddit.py
│   └── hackernews.py
├── dqc/              # DQC 邏輯（被 DAG 引用，從 ml/ import）
└── tests/
```

## DAG 寫法（用 TaskFlow API，**不要寫舊式 PythonOperator**）

```python
from airflow.decorators import dag, task
from datetime import datetime, timedelta
from pendulum import duration

@dag(
    dag_id="crawl_reddit",
    schedule="*/15 * * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    default_args={
        "retries": 3,
        "retry_delay": duration(minutes=2),
        "retry_exponential_backoff": True,
    },
    tags=["pulse", "crawl"],
)
def crawl_reddit_dag():

    @task
    def fetch_posts(subreddit: str) -> list[dict]:
        from crawlers.reddit import fetch_subreddit
        return fetch_subreddit(subreddit, limit=50)

    @task
    def upsert_posts(posts: list[dict]) -> int:
        # 寫進業務 DB
        ...

    subreddits = ["ClaudeAI", "LocalLLaMA", "ChatGPT"]
    all_posts = fetch_posts.expand(subreddit=subreddits)
    upsert_posts.expand(posts=all_posts)

crawl_reddit_dag()
```

## DAG 依賴設計

```
crawl_reddit (每 15 分鐘)
crawl_hackernews (每 15 分鐘)
        ↓
data_quality (依賴 crawl 完成，用 Dataset)
        ↓
ml_pipeline (依賴 DQC 完成)
        ↓
event_detection (依賴 ML 完成)

daily_snapshot (cron: 0 1 * * *)
weekly_report (cron: 0 8 * * 1)
```

用 Airflow Datasets 處理跨 DAG 依賴：

```python
from airflow import Dataset

POSTS_DATASET = Dataset("postgresql://db/posts")
DQC_DATASET = Dataset("postgresql://db/posts_dq_processed")

# crawl_reddit_dag 產出 POSTS_DATASET
@task(outlets=[POSTS_DATASET])
def upsert_posts(...): ...

# data_quality_dag 消費 POSTS_DATASET，產出 DQC_DATASET
@dag(schedule=[POSTS_DATASET])
def data_quality_dag(): ...
```

## 失敗處理

每個 DAG 都設：

```python
default_args={
    "retries": 3,
    "retry_delay": duration(minutes=2),
    "retry_exponential_backoff": True,
    "on_failure_callback": notify_slack,
}
```

`notify_slack` 從 Airflow Connection 取 webhook URL，發 Slack。

## 常用指令

```bash
# 列出 DAG
docker compose exec airflow-scheduler airflow dags list

# 手動觸發 DAG
docker compose exec airflow-scheduler airflow dags trigger crawl_reddit

# 查 task log
docker compose exec airflow-scheduler airflow tasks logs crawl_reddit fetch_posts 2026-05-08

# 重設 DAG 狀態（dev 用）
docker compose exec airflow-scheduler airflow db reset
```

## v3 → v4 變更

- v3 用 Prefect，v4 改用 Airflow
- 詳見 ADR-007
