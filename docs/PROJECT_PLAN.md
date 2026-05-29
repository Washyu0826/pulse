# Pulse 專案計畫書 (Project Plan)

**作者**: 冼冠宇 · Xchange · Data Project
**版本**: v3.0（個人版）
**時程**: 12 週（會動態調整）

> 完整 docx 版本見隨附檔案。本檔為 markdown 簡版，給 Claude Code 與 GitHub 訪客參考。

## 1. 動機

### 痛點

**A. AI 動態太分散** — 工程師要追 AI 進展，得同時看 Twitter、Reddit、HackerNews、Discord，每天花 30-45 分鐘還可能漏掉重要事件。

**B. 選技術 / 選工具靠玄學** — 「Claude 還是 GPT 適合做 coding agent？」每次決策要 google 半天，沒有量化依據。

**C. 趨勢觀察沒有結構化資料** — 想知道「過去 30 天 AI agent 議題的討論變化」、「DeepSeek 在 r/LocalLLaMA 的口碑走勢」，沒有現成工具。

### 一句話定義

> Pulse — AI 工程師的每日情報秘書。每天 5 分鐘掌握 AI 圈、不錯過該知道的、需要查時 30 秒給答案。

## 2. 產品定位

不是即時警示工具，也不是企業級監測平台。Pulse 是個人工程師每天打開 5 分鐘、需要時 30 秒查答案的「情報秘書」。

### 五大差異化

1. 垂直深度 — 只做 AI 模型與技術
2. 每日節奏 — 每天 5 分鐘看完，不是分鐘級警示
3. 自訂查詢 — 自由選擇時間範圍與議題
4. 結構化決策報告 — 給「該怎麼選」的明確答案
5. 趨勢回溯 — 可查歷史

## 3. 功能清單

| 編號 | 功能 | 階段 |
|------|------|------|
| F1 | 事件流首頁 | MVP |
| F2 | 預設模型即時看板 | MVP |
| F3 | 自訂查詢（議題 + 時間範圍）| MVP |
| F4 | 決策報告生成 | MVP |
| F5 | 每日模型快照 | MVP |
| F6 | 自動化資料 Pipeline | MVP |
| F7 | RESTful API | MVP |
| F8 | 發布事件偵測 | 完整版 |
| F9 | 情緒翻轉偵測 | 完整版 |
| F10 | LLM 自動報告生成 | 完整版 |
| F11 | Slack / Email 警示 | 完整版 |
| F12 | A/B Test 框架 | 完整版 |
| F13 | 系統監控 Dashboard | 完整版 |

詳細功能規格見 docx 版本。

## 4. 監測模型清單

| 模型 | 公司 | 角色 |
|------|------|------|
| GPT-5 / ChatGPT | OpenAI | 霸主 |
| Claude | Anthropic | 技術派最愛 |
| Gemini | Google | 多模態強 |
| Grok | xAI | 話題王 |
| Llama | Meta | 開源代表 |
| DeepSeek | DeepSeek | 中國攻擊者 |

## 5. 技術選型

詳見 `docs/decisions/` ADR 文件。

| 元件 | 選擇 |
|------|------|
| 後端 | FastAPI + SQLAlchemy 2.x async + Alembic |
| DB | PostgreSQL 16 |
| 排程 | Prefect 2.x |
| 情緒模型 | cardiffnlp/twitter-roberta-base-sentiment-latest |
| 主題分群 | BERTopic + sentence-transformers/all-MiniLM-L6-v2 |
| LLM 報告 | Anthropic Claude Haiku 4.5 |
| 容器化 | Docker Compose |
| 部署 | Railway |
| 前端 | Next.js 14 App Router (Server Components) |
| UI | shadcn/ui + Tailwind |
| 監控 | Prometheus + Grafana |
| CI/CD | GitHub Actions |

## 6. 資料源

- **Reddit**：praw 官方 API（免費），每日 800-1500 篇
- **HackerNews**：Algolia API（免費），每日 50-200 篇

Reddit subreddits：r/LocalLLaMA、r/ChatGPT、r/ClaudeAI、r/singularity、r/MachineLearning（主力）+ r/OpenAI、r/ArtificialIntelligence、r/LocalLLM（選配）

## 7. 預算

| 項目 | 月費 |
|------|------|
| Railway | $5 |
| Anthropic API | $20 |
| Domain | $1 |
| **合計** | **~$26** |

## 8. 12 週路線圖

詳見 `docs/TASKS.md`。

| Phase | Week | 主軸 |
|-------|------|------|
| 1 基礎建設 | 1-3 | 環境 + 資料源 + 情緒分析 |
| 2 自動化 | 4-6 | Prefect + 事件偵測 + 自訂查詢 |
| 3 上線 | 7-9 | Railway 部署 + CI/CD + 監控 |
| 4 打磨 | 10-12 | A/B test + 文件 + Demo |

## 9. 砍功能優先順序

時程嚴重落後時依序砍：
1. A/B test
2. 翻轉偵測
3. 週報 email

絕對不能砍：F1-F7（MVP）、F8 發布偵測、Prometheus 監控、Docker、CI/CD。

## 10. 給社群的價值

- 公開 API + GitHub repo
- 至少 3 篇技術 blog
- 為 AI 圈補上「個人化情報」基礎建設
