# Pulse 系統架構

> v4.0 — 採納 Mentor Review #2 建議補上的視覺化架構圖。
> 本檔案使用 Mermaid 語法，於 GitHub 自動 render。

## 1. 高層次系統架構

```mermaid
graph TB
    subgraph SOURCES["📡 資料來源層"]
        Reddit[Reddit API<br/>praw]
        HN[HackerNews API<br/>Algolia]
    end

    subgraph PIPELINE["⚙️ Airflow Pipeline (每 15 分鐘)"]
        Crawler[crawl_*_dag<br/>抓取 + UPSERT]
        DQC["data_quality_dag<br/>🛡️ DQC 5 層過濾器"]
        ML["ml_pipeline_dag<br/>情緒 + 主題"]
        Event["event_detection_dag<br/>發布 / 翻轉"]
        Daily["daily_snapshot_dag<br/>凌晨 01:00"]
        Weekly["weekly_report_dag<br/>週一 08:00"]
    end

    subgraph STORAGE["💾 儲存層"]
        PG[("PostgreSQL 16<br/>posts, sentiments,<br/>events, snapshots<br/>+ dq_runs (v4)<br/>+ evaluation_runs (v4)")]
        AirflowDB[("Airflow Metadata DB<br/>獨立 Postgres")]
        Cache[(LLM Reports<br/>Cache)]
    end

    subgraph SERVICE["🚀 服務層"]
        FastAPI[FastAPI<br/>含 RoBERTa inline]
        LLM[Anthropic API<br/>Claude Haiku]
    end

    subgraph FRONTEND["🖥️ 前端"]
        NextJS[Next.js 14<br/>Server Components]
    end

    subgraph NOTIFY["🔔 通知"]
        Slack[Slack Webhook]
        Email[Resend Email]
    end

    subgraph OBSERVE["📊 觀測"]
        Prom[Prometheus]
        Grafana[Grafana<br/>含 DQC dashboard]
        MLflow[MLflow<br/>Offline Evaluation]
    end

    Reddit --> Crawler
    HN --> Crawler
    Crawler --> PG
    PG --> DQC
    DQC -->|score >= 30| ML
    DQC -.dq_runs.-> PG
    ML --> PG
    PG --> Event
    Event -->|發布事件| Slack
    Event --> PG
    PG --> Daily
    Daily --> PG
    Daily -->|每週彙總| Weekly
    Weekly --> Email

    Pipeline -.metadata.-> AirflowDB

    PG --> FastAPI
    FastAPI --> LLM
    LLM --> Cache
    Cache --> PG

    NextJS -->|Server Components<br/>fetch + revalidate| FastAPI

    FastAPI -.metrics.-> Prom
    DQC -.dq_metrics.-> Prom
    Prom --> Grafana
    ML -.runs.-> MLflow

    classDef source fill:#F59E0B,stroke:#000,color:#fff
    classDef pipeline fill:#8B5CF6,stroke:#000,color:#fff
    classDef storage fill:#10B981,stroke:#000,color:#fff
    classDef service fill:#06B6D4,stroke:#000,color:#fff
    classDef frontend fill:#EC4899,stroke:#000,color:#fff
    classDef notify fill:#EF4444,stroke:#000,color:#fff
    classDef observe fill:#6B7280,stroke:#000,color:#fff
    classDef new fill:#FCD34D,stroke:#000,color:#000

    class Reddit,HN source
    class Crawler,ML,Event,Daily,Weekly pipeline
    class DQC new
    class PG,AirflowDB,Cache storage
    class FastAPI,LLM service
    class NextJS frontend
    class Slack,Email notify
    class Prom,Grafana,MLflow observe
```

**v4 變更標記**：
- 🟡 黃色節點 `DQC`：v4 新增的資料品質檢核
- 🟢 PostgreSQL 表新增 `dq_runs`、`evaluation_runs`
- Pipeline 框架從 Prefect 改為 Apache Airflow

---

## 2. 資料流：單篇貼文生命週期

```mermaid
sequenceDiagram
    autonumber
    participant R as Reddit API
    participant CR as crawl_reddit_dag
    participant DQ as data_quality_dag
    participant ML as ml_pipeline_dag
    participant DB as PostgreSQL
    participant E as event_detection_dag
    participant API as FastAPI
    participant UI as Next.js UI

    Note over R,UI: 一篇 Claude 相關貼文的完整生命週期

    R->>CR: praw.subreddit("ClaudeAI").new()
    CR->>CR: 過濾包含 model keywords
    CR->>DB: UPSERT posts (quality_score = NULL)

    Note over DQ: T+0 分（同批次）
    DQ->>DB: SELECT posts WHERE quality_score IS NULL
    DQ->>DQ: Layer 1: 格式檢核 (長度、刪除標記)
    DQ->>DQ: Layer 2: 語言檢測 (lingua-py)
    DQ->>DQ: Layer 3: 垃圾偵測 (bot、重複、連結農場)
    DQ->>DQ: Layer 4: 相關性 (關鍵字在正文)
    DQ->>DQ: Layer 5: 情緒可靠性預檢
    DQ->>DB: UPDATE posts SET quality_score, quality_flags
    DQ->>DB: INSERT dq_runs (摘要紀錄)

    Note over ML: T+1 分（依賴 DQC）
    ML->>DB: SELECT posts WHERE quality_score >= 30
    ML->>ML: RoBERTa 情緒分析
    ML->>DB: INSERT sentiments
    ML->>ML: BERTopic 主題分群
    ML->>DB: INSERT post_topics

    Note over DB: 每小時 / 每日彙總
    DB->>DB: sentiment_hourly UPDATE<br/>(只彙總 quality_score >= 60)
    DB->>DB: sentiment_daily UPDATE

    Note over E: 事件偵測
    E->>DB: 計算 z-score、梯度
    E->>DB: INSERT events (若觸發)
    E->>UI: Slack 通知 (Webhook)

    Note over UI: 使用者打開 dashboard
    UI->>API: GET /api/events?hours=6 (cached 60s)
    API->>DB: SELECT events JOIN models
    DB-->>API: events JSON
    API-->>UI: render Server Component
```

---

## 3. 部署架構（Railway）

```mermaid
graph LR
    subgraph Railway["🚂 Railway Pro Plan ($10/月)"]
        subgraph App["應用服務"]
            APIService[FastAPI<br/>1 replica<br/>1GB RAM]
            WebService[Next.js<br/>1 replica<br/>512MB RAM]
        end

        subgraph Airflow["Airflow 子系統"]
            AFWeb[Airflow Webserver]
            AFSched[Airflow Scheduler]
            AFMeta[(Airflow Postgres)]
        end

        subgraph Data["業務資料"]
            BizDB[(Pulse Postgres)]
        end
    end

    subgraph External["外部服務"]
        AnthAPI[Anthropic API]
        RedditAPI[Reddit API]
        HNAPI[HackerNews API]
        ResendAPI[Resend Email]
        SlackHook[Slack Webhook]
    end

    User((使用者)) --> WebService
    WebService -->|SSR fetch| APIService
    APIService --> BizDB
    APIService --> AnthAPI

    AFWeb --> AFMeta
    AFSched --> AFMeta
    AFSched -->|執行 DAG| BizDB
    AFSched -->|爬蟲| RedditAPI
    AFSched -->|爬蟲| HNAPI
    AFSched -->|週報| ResendAPI
    AFSched -->|事件| SlackHook

    classDef railway fill:#7B61FF,stroke:#000,color:#fff
    classDef external fill:#94A3B8,stroke:#000,color:#fff
    class APIService,WebService,AFWeb,AFSched,AFMeta,BizDB railway
    class AnthAPI,RedditAPI,HNAPI,ResendAPI,SlackHook external
```

---

## 4. DQC 內部流程

```mermaid
flowchart TD
    Start([新貼文進入 DQC]) --> L1{Layer 1<br/>長度 >= 20?<br/>非 [deleted]?}
    L1 -->|否| Discard[score = 0<br/>flags = [TOO_SHORT, DELETED]<br/>丟棄]
    L1 -->|是| L2{Layer 2<br/>語言 = 英文?<br/>confidence > 0.8?}
    L2 -->|否| MarkLow[score -= 20~80<br/>flag: NON_ENGLISH]
    L2 -->|是| L3{Layer 3<br/>非 bot?<br/>非重複?<br/>連結比例 < 70%?}
    L3 -->|否| MarkSpam[score -= 40~70<br/>flag: LIKELY_BOT 等]
    L3 -->|是| L4{Layer 4<br/>關鍵字在正文?}
    L4 -->|否| MarkIrrel[score -= 30<br/>flag: KEYWORD_NOT_IN_BODY]
    L4 -->|是| L5{Layer 5<br/>情緒可靠?}
    L5 -->|否| MarkUnreliable[score -= 20<br/>flag: SARCASM_DETECTED]
    L5 -->|是| Pass[score = 100<br/>flags = []]

    MarkLow --> Final
    MarkSpam --> Final
    MarkIrrel --> Final
    MarkUnreliable --> Final
    Pass --> Final

    Final{最終分數}
    Final -->|>= 60| HighQ[納入彙總、事件偵測]
    Final -->|30-59| MidQ[分析但不彙總<br/>供 debug]
    Final -->|< 30| Drop[丟棄]

    classDef pass fill:#10B981,color:#fff
    classDef warn fill:#F59E0B,color:#fff
    classDef fail fill:#EF4444,color:#fff
    class HighQ,Pass pass
    class MidQ,MarkLow,MarkSpam,MarkIrrel,MarkUnreliable warn
    class Drop,Discard fail
```

---

## 5. Offline Evaluation 流程

```mermaid
flowchart LR
    subgraph Setup["設定"]
        Models[兩個情緒模型<br/>A: twitter-roberta<br/>B: twitter-xlm-roberta]
        Ground[200 筆人工標註<br/>ground truth]
    end

    subgraph Run["評估執行"]
        Sample[從 production 抽<br/>2000 筆樣本]
        InferA[Model A 推論]
        InferB[Model B 推論]
        Compare[計算 F1, Precision,<br/>Recall, Cohen's Kappa]
    end

    subgraph Track["追蹤"]
        MLflow[MLflow Run<br/>含參數、指標、混淆矩陣]
        EvalDB[(evaluation_runs<br/>歷史紀錄)]
    end

    subgraph Decide["決策"]
        Sig{McNemar's test<br/>p < 0.05?}
        Pick[選 F1 較高者<br/>升級為 production]
    end

    Models --> InferA
    Models --> InferB
    Sample --> InferA
    Sample --> InferB
    Ground --> Compare
    InferA --> Compare
    InferB --> Compare
    Compare --> MLflow
    Compare --> EvalDB
    Compare --> Sig
    Sig -->|是| Pick
    Sig -->|否| Stay[維持現用模型]
```

---

## 6. 設計考量摘要

| 設計決策 | 為什麼 |
|---------|--------|
| Airflow 取代 Prefect | 接軌中大型企業主流，履歷加分（採納 Mentor #4） |
| DQC 在情緒分析前 | 雜訊不該進 ML pipeline（採納 Mentor #1） |
| Airflow Metadata DB 獨立 | 不與業務 DB 混用，避免互相干擾 |
| 情緒模型 inline 於 FastAPI | 個人流量規模，不需要拆獨立 service |
| DQC quality_score 三分檔 | 給「分析但不彙總」的緩衝區，避免誤殺 |
| Offline Eval 不是 A/B Test | 業界精確術語（採納 Mentor #3） |

完整決策紀錄見 `docs/decisions/`。
