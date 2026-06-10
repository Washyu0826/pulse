# 事件忠實摘要管線：四個模組怎麼組起來

> 技術核心（[個案研究](case-study-faithful-event-summarizer.md)）由四個各自獨立的純函式模組組成，再由一層膠合模組串成端到端管線。本文說明它們如何接合、附一段**不需任何重依賴**就能跑的範例，以及對範例事件的 dry-run 指令。

---

## 1. 四個模組與膠合層

| 模組 | 職責 | 注入的重模型（測試時用假的） |
|------|------|------------------------------|
| `ml/ml/event_cluster.py` | 貼文向量化 → 門檻分群成「事件」（`cluster_events`）、對單一事件群用 MMR 抽代表句（`extract_key_sentences`） | `embed_fn`（真實為 BGE-M3） |
| `ml/ml/summarize.py` | 把關鍵句組 prompt → 產生帶 inline `[n]` 引註的繁中摘要（`summarize_event`）→ 形式檢查（`validate_summary`） | `generate_fn`（真實為本機 Qwen2.5） |
| `ml/ml/faithfulness.py` | 對摘要逐句跑 NLI，量測蘊含 / 矛盾 / 引用有效性 / 來源覆蓋，匯總成 `faithfulness_report` | `nli_fn`（真實為 mDeBERTa-NLI） |
| `ml/ml/event_pipeline.py`（膠合） | 純編排：`cluster_events` → 每群 `summarize_one_event`（抽句 → 適配 → 摘要 → 忠實度），對外只有 `run_pipeline` | — 只串接上面三個注入的 callable |

組合資料流：

```
posts ──embed_fn──▶ cluster_events ──▶ 每個事件群
                                          │
                                          ├─ extract_key_sentences (embed_fn)
                                          ├─ to_summary_key_sentences  ← 引註↔來源對齊
                                          ├─ summarize_event (generate_fn) → 帶 [n] 摘要 + issues
                                          └─ faithfulness_report (nli_fn) → 忠實度分數
                                          ▼
                                EventSummaryResult（每事件一份）
```

膠合層**不引入任何重依賴**：三個模型一律由呼叫端注入（`embed_fn` / `generate_fn` / `nli_fn`），因此整條管線可在沒有 torch / FlagEmbedding / Ollama 的環境下完整離線單元測試。各階段純邏輯的測試覆蓋見 `ml/tests/test_event_cluster.py`（36）、`ml/tests/test_summarize.py`（25）、`ml/tests/test_faithfulness.py`（35）。

### 引註↔來源對齊契約

`event_cluster.KeySentence`（欄位 `text / post_index / post_id / rank`）與 `summarize.KeySentence`（欄位 `text / source_id / source`）形狀不同。膠合層的 `to_summary_key_sentences` 負責把前者適配成後者，給每個**相異來源貼文** 1-based 連續編號（同一篇的多句共用編號），`build_sources` 再依關鍵句順序排出 `sources` 清單，確保摘要裡的 `[n]`、`sources[n-1]`、第 n 條關鍵句三者編號一致。細節見 `event_pipeline.py` 檔頭。

---

## 2. 可直接跑的範例（注入假 callable，零重依賴）

下面這段把三個重模型換成確定性的假函式，因此**不需安裝任何 ML 套件、也不打 Ollama** 即可跑完整管線：

```python
import sys
sys.path.insert(0, "ml")  # 讓 import ml.* 找得到（在 D:\pulse 根目錄執行）
from ml.event_pipeline import run_pipeline

posts = [
    {"id": 9001, "text": "OpenAI 發表 GPT-5，主打更強推理。API 價格與前代相同。"},
    {"id": 9002, "text": "GPT-5 出了！聽說價格沒漲，但速度好像變慢。"},
    {"id": 9003, "text": "今天天氣真好，跟 AI 完全無關的閒聊貼文。"},
]

def fake_embed(text):
    # 假 embedder：含「GPT」的放同一邊 → 兩篇 GPT 文聚成一群、閒聊文落單
    return [1.0, 0.0] if "GPT" in text else [0.0, 1.0]

def fake_generate(prompt):
    # 假 LLM：回傳帶 [n] 引註的繁中摘要（正式為本機 Qwen2.5）
    return "OpenAI 發表 GPT-5，主打更強推理 [1]。API 價格與前代相同 [1]。"

def fake_nli(premise, hypothesis):
    # 假 NLI：回傳 entail / contradict / neutral 機率（正式為 mDeBERTa-NLI）
    return {"entailment": 0.9, "contradiction": 0.02, "neutral": 0.08}

results = run_pipeline(posts, fake_embed, fake_generate, fake_nli, threshold=0.6, min_size=2)
for r in results:
    print("members:", r.cluster.members)
    print("summary:", r.summary.text)
    print("cited_ids:", sorted(r.summary.cited_ids), "| issues.ok:", r.issues.ok)
    print("faithfulness_score:", round(r.faithfulness.faithfulness_score, 3))
```

執行後輸出（兩篇含 GPT 的貼文聚成一個事件，閒聊文因 `min_size=2` 不成群被排除）：

```
members: [0, 1]
summary: OpenAI 發表 GPT-5，主打更強推理 [1]。API 價格與前代相同 [1]。
cited_ids: [1] | issues.ok: True
faithfulness_score: 0.887
```

這段展示了關鍵設計：**換掉三個 `*_fn` 就能在任何環境跑通整條管線**——測試餵假的、正式餵真的（BGE-M3 / Qwen / mDeBERTa），編排邏輯一行都不用改。

---

## 3. 不靠 DB、單階段的 dry-run（看每事件會送什麼 prompt）

若只想看 `summarize` 這一段對真實事件素材組出的 prompt（不跑聚類、也不呼叫模型），用 `scripts/summarize_events.py` 對隨附的範例事件 fixture 做 dry-run：

```bash
python scripts/summarize_events.py docs/samples/events.sample.jsonl --dry-run
```

範例 fixture（`docs/samples/events.sample.jsonl`）是 4 個台味 AI Threads 討論事件（GPT-5 發表、Claude 訂閱調整、繁中提示詞技巧、消費級顯卡跑本地 LLM），每行一個 JSON 物件，`key_sentences` 同時示範了「帶 `source_id` / `source` 的 dict」與「純字串清單」兩種接受格式。輸出節錄：

```
📂 讀到 4 個事件：docs\samples\events.sample.jsonl

===== 事件 evt_001（prompt 預覽）=====
你是一位嚴謹的新聞編輯，負責把多則來源整理成一段忠實的事件摘要。
請用繁體中文（台灣用語）寫摘要，並嚴格遵守下列規則：
1. 只能使用「來源」區塊中編號句子裡出現的事實；不得加入任何來源沒有寫到的資訊。
2. 每個論述句的結尾，必須標註支持該句的來源編號，格式為 [n]（多個來源寫成 [1][3]）。
...
來源：
[1] OpenAI 凌晨發表新一代模型 GPT-5，主打更強的長文推理與工具呼叫能力。（來源：Threads）
[2] 官方說 GPT-5 的 API 價格與 GPT-4o 維持相同，沒有漲價。（來源：Threads）
[3] 台灣開發者實測後表示回應速度比前代略慢，但答案更穩。（來源：Threads）
[4] 也有人抱怨免費版要等到下週才開放，現在只有 Plus 用戶能用。（來源：Threads）

事件摘要：

... （evt_002 ~ evt_004 同樣印出 prompt）...

✅ dry-run 完成：印出 4 個 prompt，未呼叫模型。
```

要實際產摘要（需本機 Ollama 開著並 pull 過模型）則去掉 `--dry-run`、加 `--out`：

```bash
python scripts/summarize_events.py docs/samples/events.sample.jsonl --out summaries.jsonl --model qwen2.5:7b
```
