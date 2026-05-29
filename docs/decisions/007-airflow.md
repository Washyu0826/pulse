# ADR-007：從 Prefect 改用 Apache Airflow

**狀態**：Accepted（取代 v3 的 Prefect 決策）
**日期**：2026-05-08
**觸發**：Mentor Review 建議 #4

## 背景

v3 計畫中選用 Prefect 作為排程系統，理由是學習曲線較平緩。經過 Mentor Review 後決定改用 Apache Airflow，因為它是中大型企業的調度系統絕對主流。

## 選項

1. **維持 Prefect**（v3 原方案）
2. **改用 Apache Airflow**（v4 採納）
3. **折衷：v1 用 Prefect、v2 番外篇做 Airflow 比較 blog**

## 決定

選 **選項 2：完整改用 Airflow**。

時程從 12 週 → 14 週，預算從 $26 → $31/月。

## 理由

### 為什麼採納 Mentor 建議

1. **業界主流**：Airbnb、Lyft、Spotify、各種 Fortune 500 都用 Airflow
2. **履歷加分**：LinkedIn 招聘 filter「Airflow」配對量比「Prefect」多 5-10 倍
3. **資料工程界標準**：未來進資料工程相關職位幾乎必備
4. **學一次受用 5 年**：Airflow 2.x 穩定、不會被淘汰

### 為什麼不選折衷

折衷方案（v1 Prefect、v2 Airflow blog）雖然漂亮，但：
- 兩個都做 = 兩個都沒做精
- v2 番外篇實際發生機率 < 50%（求職一旦開始就停手）
- mentor 看到還是 Prefect 會疑惑「為什麼 v1 沒接受建議」

直接全盤改最乾淨。

## 後果

### 好處

- 履歷符合中大型企業招聘條件
- 真實學會 Airflow（DAG、Operator、XCom、Connection、Sensor）
- 跟 mentor 建議完全一致，回饋強

### 代價

- 學習曲線 1-2 週（增加 Week 5 給 Airflow 學習）
- Docker Compose 變複雜（要 webserver + scheduler + metadata DB）
- 預算多 $5/月（Railway 多服務）
- 開發初期會比 Prefect 慢

### 減輕代價的設計

- 用 **LocalExecutor**（個人專案規模適用，不需要 Celery + Redis）
- DAG 寫法用 **TaskFlow API**（Airflow 2.x 較現代寫法，類似 Prefect）
- Metadata DB 獨立 Postgres instance（不與業務 DB 混用）

## 實作要點

### Docker Compose 設定

```yaml
services:
  airflow-postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: airflow
      POSTGRES_PASSWORD: airflow
      POSTGRES_DB: airflow

  airflow-init:
    image: apache/airflow:2.9.0-python3.11
    command: db migrate
    depends_on:
      - airflow-postgres
    environment:
      AIRFLOW__DATABASE__SQL_ALCHEMY_CONN: postgresql+psycopg2://airflow:airflow@airflow-postgres/airflow

  airflow-webserver:
    image: apache/airflow:2.9.0-python3.11
    command: webserver
    ports:
      - "8080:8080"
    depends_on:
      airflow-init:
        condition: service_completed_successfully

  airflow-scheduler:
    image: apache/airflow:2.9.0-python3.11
    command: scheduler
    depends_on:
      airflow-init:
        condition: service_completed_successfully
```

### DAG 命名規則

- `crawl_reddit_dag.py`
- `crawl_hackernews_dag.py`
- `data_quality_dag.py`（v4 新增）
- `ml_pipeline_dag.py`
- `event_detection_dag.py`
- `daily_snapshot_dag.py`
- `weekly_report_dag.py`

### DAG 之間的依賴

用 Airflow 的 `ExternalTaskSensor` 或 dataset-aware scheduling：

```
crawl_*_dag (每 15 分鐘)
    ↓
data_quality_dag (依賴 crawl 完成)
    ↓
ml_pipeline_dag (依賴 DQC 完成)
    ↓
event_detection_dag (依賴 ML 完成)

daily_snapshot_dag (cron: 1:00)
weekly_report_dag (cron: Mon 8:00)
```

## 之後可能要重新考慮的情境

- 個人流量真的爆了，要 CeleryExecutor + Redis
- 想跨團隊協作（Airflow 的 RBAC 才會派上用場）
- 規模到要 Astronomer 託管
