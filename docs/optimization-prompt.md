# Pulse 全面優化 Prompt

> 這份檔案本身就是一份「可直接貼給 AI agent 執行」的提示詞（prompt）。
> 它由一次跨 api / ml / web / workers 四模組的深度稽核產生，內含具體 `file:line` 發現與分階段執行計畫。
> 使用方式：在乾淨的 session 把「角色與任務」到「驗收標準」整段貼給 agent；或逐 Phase 派工。
> 產出日期基準：2026-06-13（DB ~59.7k 篇語料，36 commits 未 push origin/main）。

---

## 角色與任務

你是一位資深的資料/ML 平台工程師，要對 **Pulse**（我自建的端到端繁中 AI 情報管線，求職作品集 + 每日自用）做一輪**全面優化**。
這不是「加功能」，而是把**既有的核心循環做到極致**：更穩、更快、更安全、更可觀測、更可重現、更能在面試現場撐住追問。

每完成一個工作項，都要：**改完 → 跑測試/建置驗證 → 用一句話回報實際結果（含數字/輸出）**，不得只說「應該可以」。

---

## 專案脈絡（必讀，決定取捨）

- **定位**：資料工程 + ML 工程**作品集**，同時是作者每天真的會打開的產品（N=1 已通過）。**前端不是首要賣點**；資料管線、自訓中文模型、離線評測、MLOps/可觀測性才是要秀的肌肉。
- **產品哲學（已拍板）**：**不做多功能，把核心循環做到極致；新功能預設不做。** 任何「不如加個 X」的衝動先擱置——除非它直接強化既有核心或修正缺陷。
- **技術核心**：事件忠實摘要（Faithful Event Summarizer，**非 RAG**）= BGE-M3 嵌入 → HDBSCAN 聚類 → MMR 抽句 → LoRA Qwen2.5-1.5B 帶引用改寫 → mDeBERTa-NLI 忠實度查核。
- **地端優先**：翻譯/蒸餾/摘要走本機 Ollama Qwen2.5，封面走本機 SD。**零雲端 LLM API、零推論成本**。優化時不得引入雲端 API 依賴。
- **繁中優先**：差異化來源是台灣 Threads（同時是分發管道）+ PTT；英文量體（HN/Dev.to）餵下游 ML/去重。
- **既有架構鐵則**：ML 邏輯寫成**純函式 + 重依賴函式內延遲載入（lazy import）+ 注入式重模型（embed_fn/generate_fn/nli_fn）**，核心邏輯不裝 torch/transformers 也能單元測試。**這個設計要保留並強化，不可破壞。**
- **5 類主題契約**：新工具 / 模型動態 / 使用方法 / 風險限制 / 倫理法規（+ 其他 fallback）。前後端、DB、測試都依賴此契約，**改動需全鏈一致**。
- **誠實標示**：README 路線圖用 ✅/🔜 誠實區分已完成 vs 進行中。優化後若狀態改變，**同步更新文件，不得灌水**。

---

## 不可違反的護欄（Guardrails）

1. **不破壞架構**：保留純函式 + lazy import + 依賴注入；不要把重模型 import 拉到模組頂層。
2. **不引入雲端 LLM 依賴**：地端 Ollama / 本機模型優先。
3. **不擅自加新功能/新頁面/新來源**：本輪是硬化既有，不是擴張。要加先在回報裡標記「建議（未做）」。
4. **不破壞 5 類主題契約與資料 schema**：動 schema 必附 Alembic migration + 全鏈（DB/api/web/test）一致。
5. **每步可驗證**：每個改動都要有對應的測試或可執行驗證；跑過再回報真實輸出。
6. **小步提交**：一個邏輯改動一個 commit，訊息用既有中文 conventional commit 風格（`fix(web): ...` / `chore(api): ...`）。先開 feature branch，不直接動 main。**未經要求不 push、不寄信、不對外發布。**
7. **先讀後改**：動任何檔案前先讀現況；發現稽核結論與現況不符，**以現況為準並回報差異**（本 prompt 的 file:line 是 2026-06-13 快照，可能已飄移）。
8. **尊重 Windows/PowerShell 環境**：主要 shell 是 PowerShell；本機慣用 API 埠 8010；雙 Python（venv 跑爬蟲、系統 Python 跑 GPU ML）。

---

## 工作方法（每個任務都照做）

`研究現況 → 規劃最小改動 → 實作 → 跑測試/建置 → 回報真實結果 → 提交`

- **驗證指令**（改完對應模組就跑）：
  - api：`cd api && uv run ruff check . && uv run mypy . && uv run pytest -q`
  - ml：`cd ml && uv run ruff check . && uv run pytest -q`（純函式，不需 GPU）
  - workers：`cd workers && uv run ruff check . && uv run pytest -q`
  - web：`cd web && npm run typecheck && npm run lint && npm run build`
- **吃真實 DB 的測試**會在無 DB 時 skip；CI 有起 PostgreSQL service。修脆弱測試時優先改成隔離 fixture，不要放寬斷言。
- **不確定就先量**：效能類改動（索引、快取、批次）要有「改前/改後」的依據（EXPLAIN、計時、bundle 大小），不要憑感覺。

---

## 優化工作流（分階段，附 2026-06-13 稽核發現）

> 依「風險 × 對作品集說服力」排序。Phase 0–1 先做（會被面試官第一眼看到的穩定性/安全）；Phase 2–3 是核心肌肉；Phase 4–5 收尾。

### Phase 0 — 安全與正確性（P0，先做）

1. **清掉預設密鑰外洩面**
   - `docker-compose.yml:13` `AIRFLOW_WEBSERVER_SECRET_KEY="pulse-dev-secret-change-in-prod"`、`AIRFLOW_FERNET_KEY` 預設空、Airflow init `admin:admin`。→ 改為從 `.env` 注入、在 `.env.example` 放「必填、需自行產生」註記，缺值時啟動即報錯（fail fast）。
2. **API 啟動期驗證必要設定**
   - `api/config.py:21-44` 所有金鑰預設空字串、無驗證 → 啟動時檢查「啟用某功能所需的 key 是否存在」，缺就明確報錯而非靜默降級。
3. **外部呼叫補 timeout**
   - `api/services/decide.py:102-108` Anthropic client 無 timeout；`api/routers/collection.py:75` Ollama 呼叫（threadpool 包裝）無 timeout。→ 都補上逾時，避免無限掛起。
4. **CORS 收緊**
   - `api/main.py:75-82` `allow_methods=["*"], allow_headers=["*"]` 且 `allow_credentials=True` 過寬 → 限定 GET/POST/OPTIONS 與必要 header。
5. **健康檢查不外洩內部錯誤**
   - `api/routers/health.py:17-18` 把原始 exception 訊息回給用戶 → 未知錯誤回通用 "unhealthy"。
6. **decide topic 參數加長度上限**
   - `api/services/decide.py:34-35` 用 ILIKE `%topic%`（SQLAlchemy 已參數化，無注入），但無長度限制易被打昂貴子字串搜尋 → Query 加 `max_length`。

### Phase 1 — 資料流可靠性與可觀測性（P0/P1，作品集主秀）

7. **對齊 Grafana 自訂指標**（不是端點不存在，是名稱沒對上）
   - `api/routers/metrics.py` 已有 Prometheus collector（`pulse_posts_total` 等）；`monitoring/grafana/provisioning/dashboards/pulse.json:47-70` 引用的 `pulse_*` 指標需與實際 endpoint 對齊；確認 Prometheus 有 scrape 到 API（`monitoring/prometheus/prometheus.yml`）。→ 讓 6 個自訂面板真的有數據。
8. **補資料新鮮度/lag 指標 + 盤中偵測**
   - 現況只有日終 `scripts/check_dataflow.py`（step 8/8，太晚）。→ 加「每來源最後抓取時間距今」指標，盤中（每 1–2h）就能發現斷流，而非晚上才知道。
9. **監控服務補 healthcheck**
   - `docker-compose.yml` 的 statsd-exporter / prometheus / grafana / cadvisor 皆無 healthcheck → 各補一個，避免啟動競態。
10. **Prometheus 告警規則**
    - 目前只 scrape 無 alert → 新增 `monitoring/prometheus/alerts.yml`：DAG 失敗、資料 lag > 閾值、scheduler 心跳消失、DB 連線池耗盡；接 Slack。
11. **daily_refresh.ps1 可靠性**
    - `scripts/daily_refresh.ps1` `$ErrorActionPreference="Continue"`，各步驟退出碼擷取但不傳遞 → 失敗步驟要能讓整體標記失敗並出聲；健康檢查的閾值（`check_dataflow.py:28-35` 硬編）標註來源與調整方式。
12. **Threads selector 脆裂處理**
    - `workers/crawlers/threads.py:170-171` DOM selector 變動會靜默回 0 筆 → 加 fallback selector + 「0 筆結果」時告警，不要無聲失敗。
13. **三個暫停 DAG 的啟用前置**：Reddit / Threads / X DAG 預設 paused，需先補憑證（`THREADS_SESSIONID` 等）。→ 在文件寫清楚啟用步驟與健康基準；**不要把憑證寫進 repo**。

### Phase 2 — 後端品質與效能

14. **消重複**：`api/services/models.py:73-76` 與 `api/services/model_detail.py:85-88` 情緒收縮公式完全重複 → 抽 `_sentiment_index(num, den, n)` 共用 helper。
15. **拆長函式**：`api/services/model_detail.py:35-186`（151 行）→ 拆 4–5 個區段 helper。
16. **補缺漏索引**：`Post.source`（`corpus.py:118` WHERE 用到）、`Theme.confident`（`feed.py:96` WHERE 用到）無索引 → 加 migration。
17. **避免取整盤再過濾**：`api/services/model_detail.py:46` 先抓全 dashboard 6 模型再用 slug 篩 → 直接查單一模型。
18. **指標查詢加上限/快取**：`api/routers/metrics.py:53-60` `posts_per_model` 無 LIMIT 隨語料成長全掃；`/metrics` 每次 scrape 重算 → 加 60s 快取或估算。
19. **統一品質閾值語意**：`api/services/_quality.py:10`（QUALITY_MIN=30）與 `api/routers/metrics.py:34-36`（60/30 分檔）語意不一致 → 收斂為單一來源常數。
20. **補型別註記**：`corpus.py:28,113`、`feed.py:64`、`_quality.py:13`、`middleware.py:28,54,58`、`metrics.py:78`。
21. **events_today 檔案來源加新鮮度檢查**：`api/routers/events_today.py` 檔案缺失時靜默回 `[]` → 至少記 warning 並回報資料時間。
22. **測試補洞**：錯誤回應（422/404）無測試；`api/tests/test_upsert_integration.py:138` 用 `asyncio.sleep(0.01)` 等時間前進（脆弱）→ 改顯式時間比較；`test_releases_integration.py` 吃真實 DB 易碎 → 改隔離 fixture。

### Phase 3 — ML 管線硬化與可重現性（核心肌肉）

23. **閾值集中化 + 附理由**：散落的 magic number 收進一處（`ml/thresholds.*` 或各模組常數），每個附「研究引用或調參依據」：`dedup.py:33-35`（SIMHASH_MAX_HAMMING=3 / JACCARD_MIN=0.8）、`data_quality.py:146-162`（扣分表）、`data_quality.py:280`（emoji>8）、`event_cluster.py:334`（threshold=0.6 / lambda=0.7）、`faithfulness.py:236-237`（entail/contradict=0.5）、`sentiment.py:41-45`。
24. **訓練可重現/可續跑**：`scripts/train_classifier.py`、`scripts/train_summarizer.py` 無 checkpoint/無中斷續跑（呼應「theme 第三次訓練曾靜默死在 94% 無 checkpoint」的事故）→ 加 `save_strategy`/best-checkpoint + 續跑；OOM 有可讀錯誤而非裸崩；確認 torch/numpy/random 三處 seed 都設。
25. **評測 async 路徑容錯**：`scripts/evaluate.py` 的 Qwen few-shot 路徑單筆失敗就整批崩 → 改逐筆 retry + 記錄失敗，不中斷整批。
26. **事件摘要端到端整合測試**：純函式（cluster/summarize/faithfulness）已用 fake 注入測得很好；缺「接真實 BGE-M3 + Ollama + mDeBERTa」的整合測試 → 加一個標記 slow/可在 CI skip 的整合測試，鎖住重模型路徑。
27. **嵌入/模型載入效率**：`scripts/evaluate.py` 每候選重載模型、推論後未釋放 VRAM → 文件標註成本，或加 `del model; torch.cuda.empty_cache()`；確認 pipeline 不重複嵌入同句。
28. **補 async 模組測試**：`distill.py` / `translate.py`（Ollama 路徑）目前無測試 → mock httpx 補單元測試。
29. **驗證統計實作（已大致正確，做回歸鎖定）**：`ml/ml/metrics.py` 的 McNemar / ECE / Brier / BH-FDR 經查公式正確 → 補/保留已知數值的回歸測試，避免日後重構破壞。

### Phase 4 — 前端品質與測試（控制投入，非主秀）

30. **單一事實來源**：6 個模型清單硬編在 `feed-filter.tsx:8-16`、`lib/site.ts:14`、`decide/page.tsx:11-18` 三處 → 收斂成一個 const 匯入。
31. **前端零測試 → 補關鍵單元測試**：`lib/` 工具（`relativeTime`、`sentimentClass/Word`、`eventToFavoritePost` 的 FNV-1a、`cn`）、`TrendChart` SVG 邊界（0/1 點、全 NaN）、`FeedFilter` URL 參數生成、`FavoriteButton` localStorage 事件。
32. **dark mode 決斷**：`tailwind.config.ts:4` 宣告 `darkMode:"class"` 但無切換/無實作 → **要嘛實作要嘛移除宣告**（依「不加功能」哲學，傾向移除以免誤導）。
33. **錯誤訊息在地化**：API 原始錯誤（如 "HTTP 404"）直接顯示給用戶 → 映射成友善繁中訊息。
34. **首頁抓取並行化（小優化）**：`app/page.tsx` 6 個 Suspense 區段各自抓取，ISR 60s 已緩解 → 可評估 `Promise.all` 預取，權衡 error boundary 顆粒度。
35. **trending 靜默失敗一致化**：`getTrending()` 失敗回 null 無提示，與 FeedSummary 不一致 → 統一降級行為。

### Phase 5 — 文件、CI 與作品集打磨

36. **架構文件去舊**：`docs/architecture.md` §1–5 仍是已 pivot 前的 v4 圖（Reddit/Anthropic API/英文情緒）→ 標清楚「已淘汰」或更新為現況，避免面試官看到自相矛盾。
37. **CI 補洞**：`.github/workflows/ci.yml` web 無單元測試（只 build）、無整合/E2E、ml/workers 無型別檢查 → 接上 Phase 4 的前端測試；評估加一個 nightly 整合測試（docker-compose 起服務跑一輪 crawl→DQC→event）。
38. **依賴可重現**：`pyproject.toml` 頂層無釘版本、無 dev/prod 分離 → 確認各子專案（api/ml/workers）有釘版本；輕/重 ML 依賴的分離寫清楚。
39. **README/路線圖同步**：本輪改動讓任何 🔜 變 ✅ 的，據實更新；不要灌水。
40. **push 與收尾**：36 commits 未 push origin/main——**在使用者明確同意後**才 push；列出本輪所有 commit 摘要供審閱。

---

## 驗收標準（Definition of Done）

- [ ] Phase 0 全數完成：無預設密鑰外洩面、外部呼叫皆有 timeout、CORS 收緊、啟動期設定驗證生效。
- [ ] Phase 1：Grafana 6 面板有真實數據、有盤中資料 lag 偵測與告警、監控服務有 healthcheck。
- [ ] api/ml/workers `ruff` + `mypy`(api) + `pytest` 全綠；web `typecheck` + `lint` + `build` 全綠。
- [ ] 新增的測試實際覆蓋本輪改動（錯誤回應、前端 lib、ML async 路徑、事件摘要整合）。
- [ ] 所有 magic number 集中且附依據；訓練可 checkpoint/續跑。
- [ ] 文件與現況一致（architecture.md 去舊、README 路線圖據實）。
- [ ] 每個 commit 原子化、訊息合既有風格；**未經同意不 push**。
- [ ] 回報一份「改了什麼、驗證輸出、剩餘建議（未做）」清單。

---

## 優先序速查表

| 順位 | 主題 | 為何先做 | 對應 Phase |
|------|------|----------|-----------|
| 1 | 預設密鑰 / 啟動驗證 / timeout / CORS | 安全與「面試第一眼」 | 0 |
| 2 | 資料流 lag 偵測 + 告警 + Grafana 對齊 | 作品集主秀＝資料工程可觀測性 | 1 |
| 3 | ML 訓練可重現/續跑 + 閾值集中 | 呼應實際事故、可重現是 ML 工程信任 | 3 |
| 4 | 後端效能（索引/快取/拆函式/消重複） | 低風險高 CP 值 | 2 |
| 5 | 事件摘要整合測試 + 統計回歸鎖定 | 鎖住技術核心不退化 | 3 |
| 6 | 前端單一事實來源 + 關鍵測試 + dark mode 決斷 | 控制投入、消歧義 | 4 |
| 7 | 文件去舊 + CI 補洞 + README 同步 | 收尾、避免自相矛盾 | 5 |

---

> **執行提示**：可一次只接一個 Phase；每個 Phase 內由上而下做，做完跑該模組驗證再進下一項。
> 遇到本 prompt 與現況不符，以現況為準並回報。遇到需破壞護欄才能完成的任務，停下來問，不要硬幹。
