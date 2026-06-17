# 開發進度記錄（2026-06-15 ~ 06-16）

> 目的：讓作者快速判斷「這幾天做了什麼、做得如何」。
> 主軸：電子報改版＋端到端打通 → 忠實事件摘要接進電子報＋每日排程 → **產品洞察 dashboard（可部署）**。
> 工作法：多 agent 並行（後端只動 `api/`、前端只動 `web/`、部署 agent 收尾，靠共用 API 合約不撞檔）。
> 每項記：**做了什麼 / 為什麼 / 怎麼驗證 / 風險與待辦**。

---

## 0. 電子報美術改版 + 端到端打通

- **做了什麼**：視覺改為**暖刊孔版印刷（Risograph）**——磚紅 `#d1495b` 套印 + 米杏紙底 `#f5efe6` + 墨黑字
  （`ml/ml/newsletter.py` 視覺 token），`cover_prompt` 改雙色套印/粗顆粒/復古 screenprint。修好題圖生成
  （系統 Python 補裝 `diffusers`；下載失敗真因是漏了 `truststore` TLS 修正，**非版本衝突，拒絕降 hf_hub**）。
  修好 SMTP 寄送（埠 465→**587 STARTTLS**）。
- **為什麼**：要有自己的美術風格 + 每天真的寄一封含生成題圖的信。
- **驗證**：`pytest ml/tests/test_newsletter.py` 31 過；**真實寄送成功**（一封含題圖的暖刊信寄到信箱）。
- **風險**：題圖 SD prompt 超過 CLIP 77 token 會截斷（僅警告）；翻譯品質仍 gist 級（見 §4）。
- **記憶/agent**：`newsletter-feature.md`、`.claude/agents/newsletter-designer.md`。

## 1. 忠實事件摘要接進電子報 + 每日排程

- **做了什麼**：忠實事件摘要 pipeline（`scripts/run_event_pipeline.py`）終於接上電子報「🗂️ 今日事件」區。
  新 `scripts/build_today_events.py`：DB 撈當日貼文 → 全地端模型（Ollama **nomic 嵌入** + **qwen2.5:7b** 生成
  繁中摘要 + **mDeBERTa NLI** 忠實度）→ `data/events_today.jsonl`（與 `/api/events/today` 共用）。
  `send_newsletter.py` 加 `_load_events_file()` 讀檔傳給 `render_html(events=...)`。接進 `daily_refresh.ps1` 第 **7/9** 步。
- **為什麼**：原本電子報把當日大事件（如 Anthropic 出口管制那串）拆散、還貼錯主題標籤；事件卡能把多篇相關
  貼文聚成一則帶**行內 [n] 出處引用**的忠實摘要——這正是專案的 NLP 核心。
- **驗證**：真實跑出當日事件（Anthropic 白宮出口管制：5 篇、忠實度 0.94，含 Axios/Reuters/WSJ 真實出處）。
- **調參發現**：nomic 嵌入下 AI 貼文彼此偏相似，分群門檻 **0.55 會把多數併成一團糊**（忠實度崩到 ~0.08）；
  **0.75 是甜蜜點**（連貫事件、忠實度 ~0.95）。未來換 BGE-M3 可再校。
- **風險與待辦**：① 事件來源**暫只取 hackernews/devto**（乾淨）；Threads 內文有 UI chrome 污染（見 §4），清掉前
  不納入在地事件。② 事件標題暫用英文原標題（翻譯差，title_zh 會把 Claude Code 音譯成「克勞德代碼」、D.C.→「D 地」）。
  ③ 門檻可能要逐日微調或換更強嵌入器才穩。

## 2. 產品洞察 dashboard `/dashboard`（給使用者，擴在現有 web app）

- **做了什麼**：
  - **後端**：新 `GET /api/dashboard/trends?days=14`（`api/api/routers/dashboard.py` + `services/dashboard.py`）回
    `theme_trend` + `sentiment_trend` 逐日時序（DB 端 group by date、補零、升冪）。其餘資料複用既有端點
    （`/api/events/today`、`/api/trending`、`/api/models`、`/api/feed/summary`）。
  - **前端**：`web/app/dashboard/page.tsx`（Server Component + ISR），複用既有元件（today-events / trending-panel /
    model-rail / feed-summary）+ 新純 SVG 堆疊面積圖（零依賴）。導覽列 + sitemap 已加。
- **為什麼**：要一個產品級、可部署的洞察門面（作品集中心），把 pipeline 產出的情報整合成單頁總覽。
- **產品級 UI/UX**：響應式（桌機多欄、行動單欄且 hero 排最前）、暗色、每區獨立載入/空/錯狀態（`friendlyError`、
  單區失敗不拖垮整頁）、a11y（語意標題、aria-label、情緒色點配可見文字）、SEO metadata。
- **驗證**：後端 `pytest api/tests/` **82 過**（含修掉「共用 dev DB 假綠」陷阱）；前端 `typecheck`/`lint`/`vitest`(50)/
  `next build` **全過**，`/dashboard` 預渲染。

## 3. 可部署（補上缺的部署面）

- **做了什麼**：原 `docker-compose.yml` 只有 db + Airflow + 監控，**無 api/web 服務、web 無 Dockerfile**。補了
  `web/Dockerfile`（Next.js standalone 多階段，327MB）+ next.config `output:'standalone'` + compose 加 `api`/`web`
  服務（內網 api 連 `db:5432`、web 用 `API_URL_INTERNAL=http://api:8000`，對外 web 3000 / api 8010）。
- **驗證（端到端）**：`docker compose build` 成功；起 api+web 後 `/api/dashboard/trends?days=7` 回 200 正確形狀，
  `/dashboard` 回 200 且**顯示真實資料**（零「暫時載入不了」、事件卡真標題+出處、6 模型+圖表+熱詞全活）。
- **部署指令**：`docker compose up -d --build db api web` → http://localhost:3000/dashboard
- **風險與待辦**：api 映像 **9.19GB**（torch 拉 CUDA build）；serving 其實不需 torch → 未來可拆 slim serving 映像，
  把 torch/ML 依賴留給訓練/事件那條。

## 4. 環境坑：Avast TLS 攔截（三處同源）

- **做了什麼/發現**：本機 Avast Web/Mail Shield MITM 攔截 TLS，三處踩到同一根源並各自解掉——
  ① **HF 模型下載**：腳本開頭 `truststore.inject_into_ssl()`（走 Windows 信任庫）。
  ② **SMTP 寄信**：用 **587 STARTTLS**（Avast 在 465 用「Untrusted Root」重簽、587 用已信任掃描根）。
  ③ **Docker build 內 npm/pip**：機器本地、**gitignored** 的 Avast 根 CA（`web/certs/`、`api/certs/`），Dockerfile
  選用性信任；乾淨 CI 無此 cert → 自動 no-op。
- **記憶**：`local-tls-smtp-gotchas.md`（三處完整解法）。

## 5. 內容品質問題（已診斷，待修）

- **發現**：檢視實際電子報內容發現三類毛病——① Threads 爬蟲 `el.text` 抓太貪，把使用者名/時間戳/回覆吞進
  `content`（污染熱詞 #小時 #分鐘、主題分類、snippet）；② 主題分類對中文 Threads 失準（個人貼/廣告歸到「使用方法」）；
  ③ 翻譯漏譯英文、音譯專名。
- **處置**：建 `.claude/agents/content-quality.md`，把 5 條 backlog（含上述）寫進去，按影響排序，待後續處理。

---

## 待辦 / 下一步

- [ ] **這批改動尚未 commit**（events 接線、dashboard、compose、Dockerfile）→ 待整理成分主題 commit。
- [ ] content-quality backlog：先修 Threads 內文抓太貪（#1，解掉後熱詞 #小時/#分鐘 會自然消失），再回頭把在地
  Threads 事件納入今日事件。
- [ ] dashboard 趨勢圖目前純 SVG 自繪、無互動 → 想要 hover tooltip / 點選篩選可再排一輪。
- [ ] 事件標題切回繁中（待翻譯品質修好，content-quality #3）。
- [ ] api serving 映像瘦身（拆 torch）。
- [ ] 兩個新 agent（newsletter-designer、content-quality）+ 既有設定，下次重開 session 才會載入成可點名類型。
