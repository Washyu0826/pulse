# Pulse 系統架構

> 本檔案使用 Mermaid 語法，於 GitHub 自動 render。
>
> ⚠️ **注意（產品已 pivot）**：下方第 1–5 節保留早期 v4 規劃圖（Reddit / HackerNews 來源、
> Anthropic API、英文 twitter-roberta 情緒），那些**已不代表現況**。專案已轉向
> **繁中優先、Threads 主力來源、地端 LLM（無雲端 API）、技術核心 = 事件忠實摘要**。
> 反映現況的圖請看 **第 5b 節（資料取得與語料庫 ~59.7k）**、**第 6 節（事件忠實摘要管線）** 與 **第 7 節（現行 Offline Evaluation 流程）**，
> 整體定位見 [README](../README.md) 與 [事件忠實摘要個案研究](case-study-faithful-event-summarizer.md)。

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

## 5b. 資料取得與語料庫（現況，~59.7k 篇）

> 反映現況的資料層。DB 已累積約 6 萬篇多源 AI 貼文；英文量體（HN / Dev.to）給下游 ML 與去重訓練量，
> 繁中在地訊號（Threads / PTT）是差異化核心與事件摘要的輸入子集。

| 來源 | 規模（約） | 語言 | 取得方式 | 程式 |
|------|-----------|------|----------|------|
| HackerNews | ~52k | 英 | Algolia API，**逐月切窗**繞單查詢 ~1000 筆上限，UPSERT 冪等可重跑 | `scripts/bulk_backfill.py` · `workers/crawlers/hackernews.py` |
| Dev.to | ~6.4k | 英 | API 翻頁（整段範圍只跑一次，避免重抓近期頁） | `scripts/bulk_backfill.py` · `workers/crawlers/devto.py` |
| **Threads** | **~1k** | **繁中（台灣）** | **Selenium 真瀏覽器 + sessionid cookie 繞登入牆；廣義 AI 門檻 + 繁體過濾擋簡中** | `workers/crawlers/threads.py` |
| PTT | ~330 | 繁中 | Selenium 真瀏覽器翻技術板 index（年齡牆板注入 over18 cookie） | `scripts/crawl_ptt.py` |

```mermaid
flowchart TD
    subgraph BULK["英文量體（回填）"]
        HN["HackerNews ~52k<br/>Algolia 逐月切窗"]
        DEV["Dev.to ~6.4k<br/>API 翻頁"]
    end
    subgraph LOCAL["繁中在地（差異化，Selenium）"]
        TH["Threads ~1k<br/>登入牆 + sessionid cookie<br/>廣義 AI 門檻 + 繁體過濾"]
        PTT["PTT ~330<br/>技術板 + over18 cookie"]
    end

    HN --> UP["upsert_posts<br/>自然鍵 on-conflict 冪等"]
    DEV --> UP
    TH --> UP
    PTT --> UP
    UP --> PG[("PostgreSQL<br/>posts ~59.7k")]
    PG --> DEDUP["跨源近似去重<br/>SimHash + token Jaccard + union-find<br/>ml/ml/dedup.py"]
    DEDUP --> DQC["DQC 多層啟發式評分<br/>ml/ml/data_quality.py"]
    DQC --> SENT["情緒 RoBERTa（GPU）<br/>ml/ml/sentiment.py"]
    DQC --> THEME["主題 5 類 zero-shot<br/>mDeBERTa-v3 · ml/ml/theme.py"]

    classDef bulk fill:#F59E0B,stroke:#000,color:#fff
    classDef local fill:#EC4899,stroke:#000,color:#fff
    classDef store fill:#10B981,stroke:#000,color:#fff
    classDef ml fill:#8B5CF6,stroke:#000,color:#fff
    class HN,DEV bulk
    class TH,PTT local
    class UP,PG,DEDUP store
    class DQC,SENT,THEME ml
```

**已跑出的下游與一個誠實發現**：HN/Dev.to 英文量體已跑完跨源去重、情緒（`cardiffnlp/twitter-roberta`，GPU）與主題（`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` zero-shot 5 類）。主題分布**嚴重偏向「新工具」**——這個偏斜正是 zero-shot 在此 taxonomy 上的弱點，也**直接成為下一步監督式微調 `hfl/chinese-macbert-base`** 取代 zero-shot 的動機（見 §7 與 [README](../README.md) 路線圖）。

**已知問題（地端 LLM）**：PyTorch GPU 推論正常（情緒 / 分類已實跑）；但 Ollama 內附的 CUDA build 目前會 crash，使需要 Ollama 的「真實模式」翻譯與摘要暫時受阻——管線純邏輯與假模型路徑不受影響。

---

## 6. 事件忠實摘要管線（現行技術核心）

> Pulse 的技術核心：把同一事件的多篇 Threads 貼文聚成叢集，抽關鍵句，用 LoRA 微調的繁中小模型
> 帶引用改寫，再經 NLI 忠實度查核。**非 RAG**。詳見 [個案研究](case-study-faithful-event-summarizer.md)。

```mermaid
flowchart TD
    A["台灣 Threads AI 貼文<br/>（已過 DQC + 繁體過濾）"] --> B["BGE-M3 嵌入<br/>event_cluster.build_bge_m3_embedder"]
    B --> C["HDBSCAN 聚事件<br/>hdbscan_cluster / cluster_by_threshold"]
    C --> D["MMR 抽關鍵句<br/>mmr_select / extract_key_sentences"]
    D --> E["LoRA Qwen2.5-1.5B<br/>帶行內引用改寫"]
    E --> F["mDeBERTa-NLI 忠實度查核<br/>faithfulness.faithfulness_report"]
    F -->|通過| G["事件摘要（帶 [n] 引用）"]
    F -->|不通過| H["標記人工複查 /<br/>降級抽取式摘要"]
    G --> I["電子報「今日事件」"]
    G --> J["自動鑄 Threads 草稿（路線圖）"]

    classDef done fill:#10B981,stroke:#000,color:#fff
    classDef wip fill:#F59E0B,stroke:#000,color:#fff
    classDef plan fill:#94A3B8,stroke:#000,color:#fff
    class A,B,C,D,F,G,H,I done
    class E wip
    class J plan
```

忠實度查核把「忠實」拆成四個可量測面向（`ml/ml/faithfulness.py`）：句級 NLI 蘊含、句級 NLI 矛盾、
行內引用有效性、來源覆蓋率，匯總成 `faithfulness_score ∈ [0,1]`。聚類 + 抽句（`ml/ml/event_cluster.py`）
與忠實度查核皆寫成**純函式 + 注入式重模型**，不裝 BGE-M3 / hdbscan / transformers 也能單元測試核心邏輯。

---

## 7. 現行 Offline Evaluation 流程（N 候選 bake-off）

> 取代第 5 節的舊版（那是英文二模型對比）。現行做法：多候選在同一 gold set 上排名 + 配對顯著性檢定。
> 程式：`scripts/evaluate.py` + `ml/ml/metrics.py`，寫入 `evaluation_runs` 表。報告範本見
> [evaluation-report-template.md](evaluation-report-template.md)。

```mermaid
flowchart TD
    subgraph Data["資料"]
        Gold["人工 gold set<br/>annotate.py（含 κ）"]
        Silver["Qwen 蒸餾 silver<br/>distill_labels.py"]
    end

    subgraph Cands["候選（多個）"]
        Base["baseline<br/>英文 zero-shot / Qwen few-shot"]
        Tuned["微調中文模型<br/>train_classifier.py (macbert)"]
    end

    Silver --> Tuned
    Gold --> Eval
    Base --> Eval
    Tuned --> Eval

    subgraph Eval["evaluate.py 評估"]
        Rank["依 macro-F1 排名 → 選 winner"]
        Sig["winner vs 各對手：<br/>McNemar + macro-F1 差 bootstrap CI<br/>+ BH-FDR 多重比較校正"]
        Cal["校準 ECE / Brier / NLL<br/>risk–coverage / AURC"]
        Rank --> Sig
        Rank --> Cal
    end

    Sig --> Rule{"差的 CI 不含 0<br/>且 BH-FDR p < 0.05?"}
    Rule -->|是| Win["宣稱顯著優勝"]
    Rule -->|否| Tie["打平 / 證據不足<br/>（重疊 CI 不算贏）"]

    Win --> Store
    Tie --> Store
    Cal --> Store
    Store[("evaluation_runs 表<br/>+ MLflow run")]

    classDef data fill:#10B981,stroke:#000,color:#fff
    classDef cand fill:#06B6D4,stroke:#000,color:#fff
    classDef eval fill:#8B5CF6,stroke:#000,color:#fff
    classDef store fill:#6B7280,stroke:#000,color:#fff
    class Gold,Silver data
    class Base,Tuned cand
    class Rank,Sig,Cal eval
    class Store store
```

這不是線上 A/B（無使用者流量分流），是 Offline Evaluation —— 多模型在同一份 labeled set 的配對比較
（見 [ADR-008](decisions/008-offline-evaluation.md)）。同一套統計（McNemar + bootstrap CI + BH-FDR）
也用於事件摘要 bake-off，只是主指標換成忠實度 + 盲測偏好。

---

## 8. 設計考量摘要

| 設計決策 | 為什麼 |
|---------|--------|
| Airflow 取代 Prefect | 接軌中大型企業主流，履歷加分（採納 Mentor #4） |
| DQC 在情緒分析前 | 雜訊不該進 ML pipeline（採納 Mentor #1） |
| Airflow Metadata DB 獨立 | 不與業務 DB 混用，避免互相干擾 |
| 情緒模型 inline 於 FastAPI | 個人流量規模，不需要拆獨立 service |
| DQC quality_score 三分檔 | 給「分析但不彙總」的緩衝區，避免誤殺 |
| Offline Eval 不是 A/B Test | 業界精確術語（採納 Mentor #3） |

完整決策紀錄見 `docs/decisions/`。
