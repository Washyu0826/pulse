# 開發進度記錄（2026-05-31 ~ 06-04）

> 目的：讓作者快速判斷「這幾天做了什麼、做得如何」。
> 主軸：定位釐清 + Threads 接入 + 主題/熱詞/翻譯三個地端 ML 功能 + 前端改版。
> 每項記：**做了什麼 / 為什麼 / 怎麼驗證 / 風險與待辦**。

---

## 0. 定位釐清（重要）

- **做了什麼**：競品分析（多 agent）→ 發現每條軸都有強勢免費對手（TLDR AI / LMSYS Arena / KWatch /
  開源 reddit-ai-trends 連中英雙語都做了）。定位收斂為 **「作品集 + N=1 實用」，差異化靠工程**，不當市場產品。
  門面採方向 C：每日實用情報（新工具/使用方法/邊界三主題），模型/情緒當篩選。
- **為什麼**：當市場產品定位 → 處處輸專門對手（這就是先前覺得「定位怪」的根因）。
- **文件**：`docs/competitor-analysis.md`、`docs/ux/positioning-c-ux.md`；記憶 `product-positioning.md`、`user-value-themes.md`。

## 1. Threads 登入爬取接入

- **做了什麼**：cookie 登入模式（`THREADS_SESSIONID`）+ 修網域（threads.net→.com）+ 修 `posted_at` 抽取
  （`<time datetime>`，原本全被當缺必填欄位丟掉）+ 補 grok + 擴大查詢 6→16 詞。`crawl_threads` DAG（每日、預設 paused）。
- **驗證**：登入模式抓到真實中文貼；累計 74 篇。
- **風險**：Threads 反爬 → 每次新貼 ~25-45（去重後），**「每天 100」屬 best-effort**；cookie 約幾週過期需重抓。
  違反 Meta ToS（次要帳號、不公開散布原文）。

## 2. 三個地端 ML 功能（全不打雲端，對齊 prefer-local-llm）

- **主題分類**：`ml/theme.py` zero-shot（mDeBERTa）→ 邊界/新工具/使用方法/其他。5195 篇已分類。
- **DQC 離題過濾**：`ml/data_quality.py` 加 OFF_TOPIC——**只對非技術來源（threads）** 套，需明確占星/寵物標記
  且無 AI 脈絡（含中文 AI 詞保護）才濾。5198 篇重評分後只濾掉 2 篇真垃圾，中文 AI 內容全保留。
- **本週熱詞**：`ml/keywords.py` OpenCC 繁→簡 + jieba 斷詞 + log-odds（Monroe）比較近 7 天 vs 30 天；
  **文章頻率(DF)** 殺單篇刷詞。`trending_keywords` 表 + `/api/trending`。真實資料抓到 opus/claude/anthropic（Opus 4.8 週）。
- **英文翻譯**：`ml/translate.py` 地端 Ollama **qwen2.5:7b**（英文指令才肯翻，OpenCC 強制繁體）；
  `translations` 表；feed 中英並列。品質 gist 級，原文兜底。
- **驗證**：各功能 backfill 跑真實資料 + 端到端 HTTP；ml 測試 keywords 5 passed、data_quality 29 passed。

## 3. 前端（定位 C 門面）

- **做了什麼**：`/api/feed`（依模型/情緒/來源/時間篩選，三主題 top N）+ 首頁三欄
  （左 依模型瀏覽 ｜ 中 今日情報 ｜ 右 本週熱詞）+ 我的最愛（localStorage 跨週留存）+ feed 預設只看今日。
- **設計**：Manus 風 → 最終 **藍色系（寶藍 #4D74EA）**、Logo（脈搏波形）、淡入/心跳動效、全寬版面、書寫體 wordmark。
- **驗證**：Next 端到端渲染、typecheck 全過。

## 4. 每日自動化

- **做了什麼**：`scripts/daily_refresh.ps1`（爬 Threads → DQC → 主題 → 熱詞 → 翻譯，各步容錯）+
  Windows 工作排程器「Pulse Daily Refresh」每日 10:00。
- **風險**：跑成功需 10:00 當下 Docker + Ollama 開著、電腦登入、cookie 未過期。

---

## 待辦 / 下一步

- [ ] 「今日」feed 目前空（資料停在 05-31）→ 靠每日排程或手動跑 `daily_refresh.ps1` 補。
- [ ] 翻譯品質：偶音譯（克勞德）、偶漏出模型碎念 → 可調 prompt / 後處理（中英並列已兜底，非急）。
- [ ] crawl_threads DAG 仍 paused、容器無 chromium（走本機排程，未走容器）→ 要走 DAG 需 `docker compose build`。
- [ ] README 差異化論述改寫對齊新定位（vs 電子報，非 vs HN 口碑/選型）。
- [ ] 熱詞長尾仍有通用英文詞 → 可加 POS 過濾 / 擴停用詞。
