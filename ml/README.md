# Pulse ML

ML pipeline 的核心邏輯，被 `api/` 跟 `workers/` 共用。

## 模組

```
ml/
└── ml/
    ├── sentiment.py        情緒分析（cardiffnlp/twitter-roberta）
    ├── topic_modeling.py   主題分群（BERTopic）
    ├── event_detection.py  事件偵測（z-score、gradient）
    ├── llm_report.py       LLM 報告生成（Claude Haiku）
    └── evaluate.py         模型評估（A/B test、historical replay）
```

## 設計原則

- **純函式為主**：能不依賴 DB 就不依賴
- **Service class 包裝重資源**：例如 `SentimentService` 載入模型
- **被 api 跟 workers 共用**：兩邊都 import `from ml.sentiment import ...`

## 用法範例

```python
from ml.sentiment import SentimentService

service = SentimentService()  # 啟動載入模型
result = service.analyze("Claude is amazing for coding")
# {"score": 0.89, "label": "positive", "confidence": 0.94}

results = service.analyze_batch([t1, t2, t3], batch_size=16)
```

## 模型清單

| 用途 | 模型 | 大小 | 載入時間 |
|------|------|------|---------|
| 情緒分析 | cardiffnlp/twitter-roberta-base-sentiment-latest | ~500MB | 10-30s |
| 主題分群 | sentence-transformers/all-MiniLM-L6-v2 | ~80MB | 5-10s |
| LLM 報告 | claude-haiku-4-5 (API) | - | - |
