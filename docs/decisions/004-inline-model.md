# ADR-004：情緒分析模型放 FastAPI 內（不獨立 service）

**狀態**：Accepted
**日期**：2026-05-08

## 背景

情緒分析模型 cardiffnlp/twitter-roberta（~500MB）要放哪。

## 選項

1. **FastAPI 內直接載入**：模型跟 API 同 process
2. **獨立 inference service**：HTTP 通訊
3. **託管服務**（Replicate、Modal）：每次 inference 付費

## 決定

選 **FastAPI 內直接載入**，eager load。

## 理由

1. **流量超低**：個人用 + 朋友看，QPS < 1
2. **MVP 求快**：12 週時程不能花時間做用不到的彈性
3. **Claude Code 友善**：一個地方改所有事
4. **省成本**：Railway 一個服務 vs 兩個服務
5. **未來要拆容易**：sentiment 邏輯包在 SentimentService class 內，要拆出來成獨立 service 也只要一週

## 後果

**好處**
- 部署簡單
- Latency 低（無 HTTP 開銷）
- Debug 容易（一份 log）

**代價**
- FastAPI 啟動慢（要載 500MB 模型，10-30s）
- 記憶體吃 1GB（Railway Pro plan 內可調）
- 多 worker 會載多份模型 → 強制 worker=1

## 重要實作原則

- **uvicorn workers=1**：避免重複載入
- **lifespan eager load**：啟動時就載好
- **包成 SentimentService class**：方便未來抽出
- **Inference 用 thread pool**：避免阻塞 async 事件迴圈
- **批次處理**：workers/ 用 batch_size=16

## 之後可能要重新考慮的情境

- Pulse 真的紅了，QPS > 100
- 想用 GPU 加速
- 要 serve 多個模型版本給不同用戶
