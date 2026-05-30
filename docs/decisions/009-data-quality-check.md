# ADR-009：Data Quality Check (DQC) 5 層過濾器設計

**狀態**：Accepted（2026-05-30 實作時部分修訂，見下）
**日期**：2026-05-08
**觸發**：Mentor Review 建議 #1

> **2026-05-30 實作修訂**（依使用者決定）：
> - **移除 Layer 2 語言檢測**（NON_ENGLISH/LOW_LANG_CONFIDENCE）—— 不做語言過濾，非英文貼文照常以相關性/互動評分。
> - **去重改為「跨來源」近似重複**（URL 正規化 + 標題 SimHash/Jaccard），非原設計的「同帳號 24h 同 hash」；
>   以 `quality_flags` 的 `DUPLICATE` + `CANONICAL:<id>` 標記，不另開表、不扣 quality_score（見 `ml/dedup.py`）。
> - 新增 spam/廣告/SEO flag（AD/SEO/AFFILIATE/CLICKBAIT/JOB_POSTING/EMOJI_SPAM…）。
> - 實作：`ml/data_quality.py`（純評分）+ `ml/dedup.py`（去重）+ `workers/pipeline/quality.py`（編排）+ `data_quality` DAG。

## 背景

Reddit / HackerNews 的原始貼文充滿雜訊：
- bot 帳號自動發文
- 純 URL、純 markdown、純 emoji
- 刪除標記（[deleted]、[removed]）
- 非英文貼文（mentor 沒提，但我加入處理）
- 重複內容（同一篇貼到多個 subreddit）
- 連結農場（內容 70% 都是連結）

直接送進情緒分析 / 主題分群 / 事件偵測會：
- 拉低情緒模型 F1
- 造成事件偵測 false positive（bot spike 被誤判為 launch）
- 污染主題分群結果（垃圾主題稀釋真實主題）

## 決定

在情緒分析前加入 **Data Quality Check (DQC) pipeline**，5 層過濾器，每筆貼文計算 `quality_score` (0-100) 與 `quality_flags` (list)。

## 5 層過濾器設計

### Layer 1：基本格式檢核（最便宜，先跑）

| 規則 | 觸發 flag | 扣分 |
|------|----------|------|
| 內容長度 < 20 字元 | `TOO_SHORT` | -50 |
| 內容 = "[deleted]" or "[removed]" | `DELETED` | -100（直接丟） |
| 純 URL（content 都是 URL）| `URL_ONLY` | -100 |
| 純 markdown（無實質文字）| `MARKDOWN_ONLY` | -80 |
| 純 emoji | `EMOJI_ONLY` | -80 |

**實作**：純 regex + 字串長度，超快。

### Layer 2：語言檢測

| 規則 | 觸發 flag | 扣分 |
|------|----------|------|
| 偵測語言 ≠ "en" | `NON_ENGLISH` | -80 |
| confidence < 0.8 | `LOW_LANG_CONFIDENCE` | -20 |

**實作**：用 `lingua-py`（比 `langdetect` 準確，短文表現好）。

為什麼用 lingua 不用 langdetect：
- langdetect 是 Google 老 lib，短文不準
- lingua 用統計方法，30 字以上 confidence 高
- lingua 支援回傳 confidence 分數，能用閾值

### Layer 3：垃圾內容偵測

| 規則 | 觸發 flag | 扣分 |
|------|----------|------|
| 用戶名 match bot pattern | `LIKELY_BOT` | -60 |
| 24h 內同帳號發 3 次以上相同內容 | `DUPLICATE_CONTENT` | -70 |
| 內容連結比例 > 70% | `LINK_HEAVY` | -40 |
| 含已知 spam phrase | `SPAM_PHRASE` | -50 |

**Bot pattern**：
```python
BOT_USERNAME_PATTERNS = [
    r"bot[_-]?\d*$",          # xxx_bot, xxx-bot, botxxx123
    r"^auto[_-]",             # auto_xxx, auto-xxx
    r"[_-]bot$",              # xxx-bot, xxx_bot
    r"^AI[_-]?\d+",           # AI_123, AI123
    r"[_-]gpt[_-]?\d*$",      # xxx_gpt, xxx-gpt-4
]
```

**重複偵測**：
- 計算內容 SHA256 hash
- 查 `posts` 表近 24 小時是否有同 hash 同作者
- 用 Redis cache 加速（之後加，v1 直接查 DB）

**連結比例**：
```python
url_chars = sum(len(m.group()) for m in URL_REGEX.finditer(content))
ratio = url_chars / len(content)
```

### Layer 4：相關性檢核

| 規則 | 觸發 flag | 扣分 |
|------|----------|------|
| 不含任何模型 keyword | `NO_KEYWORD` | -100（直接丟） |
| keyword 只在 URL / code block | `KEYWORD_NOT_IN_BODY` | -30 |
| keyword 出現 1 次（提到但非主題）| `WEAK_KEYWORD` | -10 |

**「keyword 在正文」判斷**：
1. 去除 URL、markdown link、code block 後的文字
2. 在剩餘文字裡 search keyword
3. 找不到 → flag KEYWORD_NOT_IN_BODY

### Layer 5：情緒可靠性（推論前預檢）

| 規則 | 觸發 flag | 扣分 |
|------|----------|------|
| 含大量反諷 marker | `SARCASM_DETECTED` | -20 |
| 全大寫（疑似 spam）| `ALL_CAPS` | -15 |

**反諷 marker**：
```python
SARCASM_MARKERS = [
    "/s",                    # Reddit 反諷標記
    " lmao ", " lol ",       # 結尾後綴
    "oh great another",
    "wow, just wow",
    "what a surprise",
]
```

注意：Layer 5 不是丟棄，是 **flag 起來給 debug 用**。反諷的情緒分析模型本來就會出錯，標起來方便人工 review。

## 分數處理規則

```
score = max(0, min(100, 100 + sum(layer_deductions)))

if score >= 60:
    # 高品質：納入彙總、事件偵測、每日快照
    HIGH_QUALITY
elif score >= 30:
    # 中品質：分析但不彙總（供 debug 與離線評估用）
    MID_QUALITY
else:
    # 低品質：完全丟棄
    DISCARD
```

## 資料庫變更

```sql
ALTER TABLE posts ADD COLUMN quality_score INT NULL;
ALTER TABLE posts ADD COLUMN quality_flags TEXT[] DEFAULT '{}';
ALTER TABLE posts ADD COLUMN dq_processed_at TIMESTAMP NULL;

CREATE INDEX idx_posts_quality ON posts(quality_score);
CREATE INDEX idx_posts_dq_unprocessed
    ON posts(fetched_at) WHERE dq_processed_at IS NULL;

-- DQC 執行摘要
CREATE TABLE dq_runs (
    id              BIGSERIAL PRIMARY KEY,
    airflow_run_id  VARCHAR(255),
    posts_processed INT NOT NULL,
    posts_high_quality INT NOT NULL,    -- score >= 60
    posts_mid_quality  INT NOT NULL,    -- 30 <= score < 60
    posts_low_quality  INT NOT NULL,    -- score < 30
    flag_distribution  JSONB NOT NULL,  -- {"TOO_SHORT": 23, "NON_ENGLISH": 45, ...}
    avg_processing_ms FLOAT,
    created_at      TIMESTAMP DEFAULT NOW()
);
```

## Airflow DAG 設計

```python
@dag(
    schedule="*/15 * * * *",
    start_date=datetime(2026, 5, 1),
    catchup=False,
    tags=["data-quality"],
)
def data_quality_dag():

    @task
    def fetch_unprocessed_posts():
        # SELECT posts WHERE dq_processed_at IS NULL LIMIT 500
        ...

    @task
    def run_quality_check(posts):
        # 5 層過濾，回傳 (post_id, score, flags) tuples
        ...

    @task
    def update_posts(results):
        # UPDATE posts SET quality_score, quality_flags
        ...

    @task
    def record_run_summary(results):
        # INSERT dq_runs
        ...

    posts = fetch_unprocessed_posts()
    results = run_quality_check(posts)
    update_posts(results)
    record_run_summary(results)
```

## 監控指標（Grafana）

- 每日高品質貼文比例（目標 > 60%）
- 各 flag 觸發次數（找出異常突起）
- DQC 平均處理時間（單篇 < 50ms）
- 各模型的高品質貼文數（看哪個模型最多雜訊）

## 預期效益

- 情緒模型 F1 從預估 0.73 → **0.81+**
- 事件偵測 false positive 降低 30%+
- 履歷量化指標：
  - 「DQC 後處理量降 30%，信號雜訊比提升 2 倍」
  - 「Bot 偵測 precision 92%，誤殺率 < 3%」

## 風險與緩解

| 風險 | 緩解 |
|------|------|
| DQC 太激進誤殺好資料 | 保留 score 30-59 區間「分析但不彙總」，可事後復原 |
| Bot pattern 漏抓 | 每月人工檢查 100 筆，補新 pattern |
| 語言檢測誤判 | lingua confidence < 0.8 只標 flag，不直接丟 |
| 重複偵測誤殺正常 repost | 限制「同帳號 24h 內」3 次，跨帳號 repost 不算重複 |

## 之後可能要重新考慮的情境

- 支援多語言（中、日、韓 AI 圈也很活躍）→ Layer 2 規則要改
- Pulse 商用化、要更嚴的 SLA → 加機器學習版的 bot 偵測（HMM、隔離森林）
- 加 LLM-based quality check（讓 Haiku 判斷品質）→ 成本太高，目前不做
