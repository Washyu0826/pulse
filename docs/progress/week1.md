# Week 1 開發進度記錄

> 目的：讓作者（冠宇）快速判斷「這週做了什麼、做得如何」。
> 對應 `docs/TASKS.md` 的 Week 1：Reddit API + Models + Posts + Migration + 爬蟲。
> 每個階段都記：**做了什麼 / 為什麼這樣設計 / 怎麼驗證 / 風險與待辦**。

---

## 階段 0：技術研究（完成 ✅）

用兩個並行研究 agent 調查，再對照本地 ADR 定案：

### 研究 A — SQLAlchemy 2.x + Alembic（重點結論）
- 用 `Mapped[...]` + `mapped_column()`；nullability 由型別標註決定（`Mapped[int]` = NOT NULL，`Mapped[int | None]` = nullable）。
- 想在 DB 層生效的預設值用 **`server_default`**（Alembic 只會把 server_default 寫進 migration）。
- 時間戳用 **`timestamptz`**（`DateTime(timezone=True)` + `server_default=func.now()`）。ADR-009 原本寫裸 `TIMESTAMP`，升級為 timezone-aware。
- **在第一個 migration 前**就替 `Base.metadata` 設好 `naming_convention`，否則日後改約束名很痛。
- `quality_flags TEXT[]` 用 **PG dialect 的 `ARRAY(Text)`**（不是泛用 `sqlalchemy.ARRAY`）；JSONB 用 `postgresql.JSONB`。
- Alembic `env.py` 既有設定是 **sync（正確）**，但有兩個缺口要補：
  1. 沒 import model 模組 → autogenerate 偵測不到任何表。
  2. 缺 `compare_server_default=True` → server_default 變更會被漏掉。
- **`onupdate=func.now()` 在 UPSERT / bulk UPDATE 不會觸發** → upsert 的 `set_` 要顯式塞 `updated_at=func.now()`。

### 研究 B — asyncpraw 爬蟲（重點結論）
- Read-only 只需三個 credential（client_id / secret / user_agent），**不需要** 帳密登入。
- 一定要 `async with asyncpraw.Reddit(...)` 包起來，否則 aiohttp session 洩漏。
- 用 **`.new(limit=)`**（時間序）做週期性爬蟲，不要用 `.hot()`（會一直重抓熱門文）。
- `author` 帳號被刪會是 `None` → 必須 `sub.author.name if sub.author else None`，否則中途 crash。
- 去重交給 **DB UPSERT**（key = `source` + Reddit `id`），不要自己做 client-side 分頁。
- 重試只重試「暫時性」例外：`ServerError` / `RequestException` / `TooManyRequests`；`Forbidden`/`NotFound` 不重試（私密/封鎖的 subreddit）。
- 爬蟲只存 **raw**（`quality_score=NULL`），**不要** 在這裡丟棄 `[deleted]` 或做關鍵字過濾正文 —— 那是 Week 3 DQC 的事（ADR-009）。

完整研究全文見本次對話記錄（含官方文件來源連結）。

---

## 階段 1：資料庫 Schema（完成 ✅）

**做了什麼**
- `api/database.py`：替 `Base.metadata` 加 `NAMING_CONVENTION`（pk/uq/fk/ix/ck），讓 migration 約束名穩定可逆。
- `api/models/mixins.py`：`TimestampMixin`（created_at / updated_at，timestamptz + server now()）。
- `api/models/models.py`：`Model`（6 模型主表，含 slug/name/company/role/aliases）+ `PostModel`（posts↔models 多對多關聯表）。
- `api/models/posts.py`：`Post` 原始貼文表。
- `api/models/__init__.py`：集中 re-export，讓 Alembic 一次抓到所有表。

**為什麼這樣設計**
- **多對多**（post_models）而非單一 model_id：一篇貼文常同時提到多個模型，Week 2 `/api/models/{slug}/posts` 查詢更乾淨。
- **(source, external_id) 唯一鍵**：跨來源（reddit/HN）去重，UPSERT 的衝突目標。
- **三種時間戳分離**：posted_at（來源發佈）/ fetched_at（首次抓取，DQC 找未處理用）/ created_at·updated_at（row 稽核）。
- **DQC 欄位**（quality_score nullable、quality_flags TEXT[]、dq_processed_at）+ partial index `WHERE dq_processed_at IS NULL`，完全對齊 ADR-009。

## 階段 2：Alembic Migration（完成 ✅）

- 修 `alembic/env.py`：import `api.models`（補上 autogenerate 抓不到表的缺口）、加 `compare_server_default=True`、URL 退回 `settings`。
- `alembic revision --autogenerate` 產出 `5099a2f34ecc`：3 張表 + 4 索引 + partial index + CASCADE FK 全部正確。
- `alembic upgrade head` 套用成功，`\dt` 確認 4 張表（含 alembic_version）。
- **修了 2 個 Windows 跨平台 bug**（見下方「踩到的坑」）。

## 階段 3：Reddit 爬蟲（完成 ✅）

- `workers/crawlers/reddit.py`：`crawl_reddit()` async generator，read-only、單一 Reddit instance 循序抓、tenacity 重試（只重試暫時性例外）、per-post 錯誤隔離。
- 純函式 `match_models()`（詞界關鍵字比對）、`normalize_submission()`（欄位正規化、刪號 author=None、UTC）→ 可單元測試、不碰網路。
- `api/services/posts.py`：`upsert_posts()` 批次 UPSERT + 建關聯（批內去重、必填防護、未知 slug 記 log、關聯數正確計算）。
- `scripts/seed_models.py`：seed 6 模型（idempotent）。
- `scripts/test_crawl.py`：手動測試（爬 → upsert → 印統計）。

## 階段 4：Code Review（完成 ✅）

派獨立 review agent 嚴審，評為「above-average Week 1，schema 是亮點」。命中 3 個 must-fix，**全部已修**：
1. ✅ `upsert_posts` 零測試 → 補 6 個整合測試（批內去重、on-conflict 更新、updated_at 推進、關聯不重複、未知 slug、必填略過）。
2. ✅ 爬蟲 `except Exception` 太寬（一篇壞文丟掉整個 subreddit）→ 改 per-post try/except + subreddit 層只攔 `AsyncPrawcoreException`。
3. ✅ `stats["associations"]` 重跑會謊報 → 改用 `.returning()` 計實際新增數。

順手修的 should-fix：必填欄位防護、`slug_to_id` 屬性存取、未知 slug 記 log、partial index WHERE 斷言、`skipped` 統計。

## 階段 5：手動驗證（完成 ✅）

| 驗證項 | 結果 |
|--------|------|
| Postgres 啟動 + migration | ✅ 4 張表建成，partial index / unique / FK 都在 |
| Seed 6 模型 | ✅ DB 查到 gpt/claude/gemini/grok/llama/deepseek + aliases |
| 單元測試（schema 7 + 爬蟲 11） | ✅ 18 passed |
| 整合測試（upsert，真 Postgres） | ✅ 6 passed |
| ruff lint | ✅ All checks passed |
| 跨套件 import + 無憑證友善報錯 | ✅ |
| **真實 Reddit 爬取** | ⏳ 需你的 Reddit API key（唯一未跑項）|

**對照 TASKS.md Week 1 驗收**：Postgres+migration ✅、能抓存 DB（程式+測試就緒，待真 key）⏳、首頁 6 卡片（既有）✅、OpenAPI ✅。

---

## 踩到的坑（給未來的自己 + 寫進 blog 的素材）

1. **本機 PG18 佔 5432**：Docker pulse-db 只搶到 IPv6，`localhost` 解析混亂 → 認證失敗。
   解法：docker host 埠改 **5433** + 連線用 **127.0.0.1**（強制 IPv4）。已改 docker-compose / .env.example / config.py。
2. **Windows cp950 讀 alembic.ini**：configparser 用 OS locale 編碼讀 .ini，中文註解 → `UnicodeDecodeError`。
   解法：`.ini` 保持 **ASCII-only**（.py 不受影響，預設 UTF-8）。
3. **Windows console cp950 印中文/emoji crash**：腳本加 `sys.stdout.reconfigure(encoding="utf-8")`。
4. **alembic ruff hook**：`console_scripts` entrypoint 找不到 → 改 `exec` 模式。
5. **pytest-asyncio 跨 event loop**：module-scope async engine + function-scope test loop → asyncpg `another operation in progress`。解法：engine fixture 改 function scope。

## 開發環境備註

- 本次用輕量 `.venv`（只裝 Week 1 需要的套件，避開 torch/transformers 數 GB）驗證；正式環境仍用 `uv sync`。
- DB host 埠是 **5433**，連線字串用 `127.0.0.1`。

## 已知待辦（非 Week 1 blocker，留給後續）

- post_models 加 ORM `relationship()`（Week 2 `/api/models/{slug}/posts` 會用到）。
- slug/aliases 三處重複（MODEL_KEYWORDS / SEED_MODELS / DB）→ 收斂成單一來源。
- CI 尚未跑 workers 測試（避免裝 airflow 重依賴）；api CI 已涵蓋 schema + 整合測試。
- `quality_score` 可加 `CHECK (0..100)`（Week 3 DQC 前）。

---

## 階段 6：HackerNews 來源（Week 2 提前 ✅）+ CI 修復

**背景**：暫時拿不到 Reddit API key，改先做計畫內的第二來源 HackerNews（Algolia API，零 key），打通「真實資料 → DB」。

**做了什麼**
- `workers/crawlers/keywords.py`：抽出共用的關鍵字比對（收斂 review 指出的「slug 三處重複」），reddit/hackernews 共用。
- `workers/crawlers/hackernews.py`：`crawl_hackernews()`，走 Algolia `/search_by_date`、httpx + tenacity（429/5xx 才重試）、跨關鍵字去重、per-hit 錯誤隔離。輸出與 Reddit 同形狀 → **共用 upsert_posts**。
- `scripts/test_crawl.py`：支援 `--source hackernews|reddit`；加 best-effort `truststore` 注入（見下方坑 6）。
- 測試：HN 6 純函式 + 3 async generator（去重/失敗隔離/關鍵字過濾）= workers 共 **20 passed**。

**真實資料驗證（重點成果）**
| 項目 | 結果 |
|------|------|
| 實際爬 HN | ✅ 201 篇進 DB、261 個 post↔model 關聯 |
| 模型分佈 | claude 105 / gpt 67 / gemini 41 / deepseek 26 / llama 19 / grok 3 |
| 抽樣合理性 | ✅「Claude Opus 4.8」1472 分等真實貼文 |
| 冪等性 | ✅ 再跑一次 upserted 201 / associations 0，DB 無暴增 |

**Code review（第二輪，HN）**：評「solid，無 Critical」。採納 4 個 must-fix：
1. ✅ `title=None` 保留 None（交給必填防護略過）而非塞 ""，與 Reddit 一致 + 回歸測試。
2. ✅ retry 加 429（限流退避）。
3. ✅ 補 `crawl_hackernews` async generator 測試（去重 + 單一 term 失敗隔離 + 關鍵字過濾）。
4. ✅ docstring 對齊 `search_by_date`、標註「只抓第 0 頁、term 間不節流」。

**CI 修復（你回報的紅燈）**
- **API exit 2 主因**：CI 的 `uv sync` 不裝 optional dev 依賴 → `uv run ruff` 找不到。改 `uv sync --extra dev`。
- **ruff violations**：`api/` 內跑 `ruff check .` 把 `api` 當 first-party，import 排序規則與我先前不同；另有 `Union`→`|`、`Sequence` from collections.abc。已 `--fix`。
- **B008 誤報**：`Depends()` 放參數預設是 FastAPI 慣例 → pyproject 加 `flake8-bugbear.extend-immutable-calls`。
- **未來 migration 不再壞 CI**：alembic post_write_hook 加 `ruff check --fix`（不只 format）。
- **Web 失敗**：缺 `package-lock.json` → `npm ci` 必敗。改用 `npm install` + 移除快取（本機網路被 TLS 攔截無法生成 lock，留 TODO 之後補）。

## 踩到的坑（續）

6. **企業/校園網路 TLS 攔截**：httpx/pip/npm 都報 `CERTIFICATE_VERIFY_FAILED`（根憑證在 OS 但不在 Python 信任庫）。解法：`truststore.inject_into_ssl()` 改用 OS 信任庫 → 立刻通。已加進 workers 依賴 + test_crawl.py（best-effort）。

---

## 階段 7：發布事件偵測來源 HF + GitHub（F8 打底，Week 7 提前 ✅）

**目標**：加兩個零 key 的「發布訊號」來源，餵 F8 發布事件偵測，做出「multi-source event detection」。

**設計**：發布訊號與討論貼文性質不同 → 建**專屬 `release_events` 表**（非塞進 posts）。
- `release_events`：source / external_id / model_id(FK,可空) / title / url / repo / kind / version / published_at / extra(JSONB)。unique(source, external_id)。
- migration `07c2dc252310`（autogenerate，post-write hook 自動 ruff，驗證了 alembic.ini 修正）。

**做了什麼**
- `crawlers/_http.py`：共用 httpx 重試（逾時/5xx/429）；HN 也改用它（消重複）。
- `crawlers/huggingface.py`：逐 org 查 `createdAt desc` 最新模型（HF Hub API，零 key）；google 只收 gemma；org/per-model 錯誤隔離。
- `crawlers/github.py`：逐 repo 抓 releases（60/hr 循序、可選 GITHUB_TOKEN）；404→[]、draft 跳過、prerelease 標記。
- `keywords.py`：加 `HF_ORG_TO_SLUG` / `GITHUB_REPO_TO_SLUG`（依研究實測對應）。
- `api/services/releases.py`：`upsert_release_events`（slug→model_id 解析、批內去重、必填防護、冪等）。
- `api/routers/releases.py`：`GET /api/releases/recent`（**第一個業務 endpoint**，含 source 篩選 + model slug）。
- `scripts/fetch_releases.py`：手動抓取腳本。

**真實資料驗證**
| 項目 | 結果 |
|------|------|
| 實際抓 HF + GitHub | ✅ 198 筆進 DB（HF 138 model_upload + GitHub 60 release）|
| 分佈 | HF: llama 60/deepseek 30/gpt 30/gemini 16/grok 2；GitHub: claude 20/gpt 20/gemini 10/llama 8/deepseek 2 |
| 抽樣 | ✅ claude-code v2.1.156（當日）、openai codex alpha、anthropic SDK 等真實版本 |
| 冪等性 | ✅ GitHub 再跑 received 60 / upserted 60（更新非新增）|

**Code review（第三輪）**：評「solid, production-quality，無 Critical/High」。採納 must-fix：
1. ✅ 補 `model_id` on-conflict 更新的回歸測試。
2. ✅ 文件化 GitHub 60/hr 請求預算（勿低於 10 分鐘一次）。
3. ✅ 文件化 HF 無 high-water mark（F8 用 published_at 判斷新發布）。
4. ✅ HN 改用共用 `_http`（消重複）；endpoint `source` 改 `Literal`（給 422 而非空結果）。

**測試**：API 20（+release 整合 7）+ workers 31（+HF/GitHub 12）= **51 passed**，ruff 全過。

**現況**：後端有**第一個業務 endpoint** `/api/releases/recent`，回真實發布事件 —— F8 的高精度訊號面已可用。前端尚未接（下一步可做垂直切片）。

---

## 階段 8：前後端垂直切片 ✅（首頁顯示真實發布事件）

**目標**：把前端接上 `/api/releases/recent`，讓首頁顯示真實資料（取代假卡片），證明端到端鏈路。

**做了什麼**
- `web/lib/types.ts`：`ReleaseEvent` DTO 型別（前後端對應單一來源）。
- `web/lib/api.ts`：`getRecentReleases()` —— Server Component 用的 typed fetch，`next: { revalidate: 60 }`（ISR）；**任何失敗都回 `{ ok:false }`，不 throw 整個 route**；驗證回應是陣列。
- `web/components/release-card.tsx`：純展示卡片（Server Component），`Intl.RelativeTimeFormat` 相對時間（無依賴）、source/model/version 標籤、安全外連（`rel="noopener noreferrer"`）。
- `web/app/page.tsx`：首頁改 `await getRecentReleases(20)`，三態渲染（失敗 / 空 / 列表）。

**端到端驗證（重點成果）**
| 項目 | 結果 |
|------|------|
| API endpoint 實測 | ✅ `/api/releases/recent` 回 200、依時間排序、`source` 篩選、invalid source → 422 |
| 前端 typecheck / lint / build | ✅ 全過，首頁預渲染為靜態（ISR 60s） |
| **`next start` 抓首頁 HTML** | ✅ 含真實資料：`anthropics/claude-code`、版本 `v2.1.156`/`v0.105.2` 等 render 出來 |
| 完整鏈路 | ✅ 瀏覽器 → Next.js SSR → FastAPI → PostgreSQL → 真實 HTML |

**Code review（第四輪）**：評「solid, honest vertical slice」。採納 must-fix：
1. ✅ `api.ts` 驗證回應為陣列（200 但非陣列不再讓 `.map` crash）。
2. ✅ `ApiResult` 改真正的 result type（失敗分支不帶 data，型別強制先檢查 ok）。
3. ✅ `relativeTime` 加 `NaN` 防護（壞時間不顯示 "NaN 天前"）。
4. ✅ server 端優先用 `API_URL_INTERNAL`（容器部署 server/browser URL 分離）+ 註記。

**工具坑**：sandbox 的 npm 也被 TLS 攔截 → 用 Node 24 的 `NODE_OPTIONS=--use-system-ca`（等同 Python truststore）解決，順利 `npm install` 並產生 `package-lock.json`。

**CI**：有了 lock file → web job 改回 `npm ci` + setup-node 快取（解掉先前的 TODO）。

**現況**：首頁已顯示**真實發布事件**。本機跑法：
```
# 1) 起 DB + API
docker compose up -d db
cd api && uv run uvicorn api.main:app   # 或用 .venv
# 2) 起前端
cd web && npm install && npm run dev     # 開 http://localhost:3000
```

---

## 階段 9：新增討論來源 Dev.to + Lobsters ✅（Reddit 暫不可用的替代）

**背景**：Reddit 目前不可用，加兩個免 key、作者/連結可追溯的「AI 使用評論/分享」來源。

- `crawlers/devto.py`：Forem 官方 API（`/articles/latest?tag=...`），逐 tag 抓、跨 tag 去重。
- `crawlers/lobsters.py`：`lobste.rs/t/ai,ml.json`，小社群站 → 低頻、帶可聯絡 User-Agent。
- 兩者沿用 `_http` 重試 + `match_models` 過濾（tag 當抓取範圍、關鍵字當保留關卡），共用 `upsert_posts`。
- `scripts/test_crawl.py` 加 `--source devto|lobsters`。

**真實資料**：Dev.to 140 篇（claude 83/gpt 69/gemini 14…）、Lobsters 1 篇（社群小、量少但正常）。
**DB 現有 5 來源**：HN 201 + Dev.to 140 + Lobsters 1（posts 342）+ HF 138 + GitHub 60（release_events 198）。

**Code review（第五輪）**：採納 Medium must-fix —— `str(None)` 會變字串 `"None"` 騙過必填防護，
改為缺 id 時保留 `None`（devto + hackernews 同源 bug 一併修），並補測試。workers 43 測試全過。

> 註：F8 事件偵測（z-score/spike）研究已完成（modified z-score median/MAD + 最小數量門檻），
> 待後續實作；現在多來源資料更豐富，偵測會更準。

---

## 階段 10：F8 事件偵測 ✅（z-score 突增 + 發布事件）

**目標**：把 posts + release_events 變成偵測到的「事件」，寫進 `events` 表，開放 `/api/events`。

**演算法（ml/ml/event_detection.py，純函式可測）**
- 討論量突增：**穩健 modified z-score（median/MAD）**，比 mean/std 抗離群（過去突增不會遮蔽下一次）。
  trailing window 14 天且**排除當天**、缺日補 0、絕對門檻 min_count=5、MAD=0 以 floor 防除零、severity 封頂 10、暖身期不發。
- 發布事件：release_events 依 (模型, 日) 聚合（過濾 GitHub prerelease 降噪、帶 kinds）。

**實作**
- `api/models/event.py` + migration `1691c8174801`：`events`（dedup_key 唯一＝冪等鍵、score Float、extra JSONB、FK SET NULL）。
- `api/services/events.py`：`upsert_events`（dedup_key 衝突更新、slug→model_id、未知 slug 警告）。
- `api/routers/events.py`：`GET /api/events`（type/model 篩選、occurred_at+id 穩定排序）。
- `scripts/run_event_detection.py`：讀 DB → 偵測 → upsert。

**真實資料成果**
| 項目 | 結果 |
|------|------|
| 偵測 | discussion_spike **11** 筆 + launch **92** 筆，冪等（重跑 upsert 不增） |
| 招牌案例 | **Claude 討論量 5/26→5/29 連爆（19→40→65→36 篇，平日中位 1）→ severity 封頂 10**（Opus 4.8 發布帶動）|
| 也抓到 | gemini 5/22（15 篇）、gpt 5/20（10 篇）等 |

**Code review（第六輪）**：評「數學正確，無 Critical/High」。採納 must-fix：
1. ✅ 端點加 `id` tiebreak（同日事件排序穩定）。
2. ✅ launch 降噪：過濾 GitHub prerelease + extra 帶 kinds。
3. ✅ 補測試：down-spike 不誤判、severity 封頂、window 防呆、launch kinds。
4. ✅ upsert 未知 slug 警告（對齊 releases）；outer-join 篩選行為加註解。

**測試**：ML 15 + API 25 + workers 43 = **83 passed**，ruff 全綠。後端業務 endpoint 增至 2 個（/api/releases、/api/events）。

> 待精修（非阻塞）：偵測未刪除「不再被偵測到」的舊事件（目前只 upsert）；launch HF re-upload 量仍偏多，未來可用 downloads 門檻再降噪；sentiment_flip 偵測待 Week 4 情緒分析後補。

---

## 階段 11：前端接事件流 ✅（F8 看得見）

**目標**：首頁加「事件流」區塊，顯示 `/api/events` 偵測到的突增 + 發布。

- `lib/api.ts`：重構成泛型 `fetchArray<T>`（消除重複），加 `getRecentEvents`。
- `lib/time.ts`：抽出共用 `relativeTime`（release-card 也改用，去重）。
- `components/event-card.tsx`：事件卡（突增=琥珀 Activity / 發布=青 Rocket，spike 顯示 severity）。
- `components/section-status.tsx`：抽出空/錯狀態框（消除 page 內 4 處重複）。
- `app/page.tsx`：`Promise.all` 並行抓 events + releases，事件流置頂；各區塊獨立守 ok。

**端到端驗證**：typecheck/lint/build 全過；`next start` 首頁 HTML 渲染出**真實偵測事件**
（「討論突增」標籤 + severity + 真實篇數 65/40/36/19）。

**Code review（第七輪）**：評「無 Critical/High，可合併」。採納 polish：修 release 區塊錯誤文案、
抽 SectionStatus 去重、`result`→`releases` 改名、meta 對比度 /40→/50（WCAG）。

**現況**：首頁三段都是真實資料 —— **事件流（F8 突增/發布）** + 最新發布事件 + 6 模型看板（看板待接）。

---

## 階段 12：歷史資料回填（4~5 月）+ 修真實上線 bug ✅

**目標**：回填 2026-04~05 的歷史資料，讓時間序列夠密、F8 偵測更有意義。

**爬蟲強化**
- `hackernews.py`：加 `since/until/max_pages` —— 用 Algolia `numericFilters(created_at_i)` 做**精準日期範圍** + 分頁；`_epoch` tz-safe（naive 視為 UTC）。
- `devto.py`：加 `since/until/max_pages` —— `/articles/latest` 往回翻頁，整頁早於 since 即停（半開區間 [since, until)）。
- `scripts/backfill.py`：回填協調器。

**踩到並修掉的真實上線 bug（重要）**
- **PG 32767 bind 參數上限**：一次塞 5000+ 列 INSERT → asyncpg 報 `cannot exceed 32767`。
  修法：抽 `api/services/_batch.py` 的 `chunked()`，**三個 upsert 服務全部分塊**（posts/releases/events），單一交易末尾才 commit（保持原子性）。

**回填成果（實測）**
| 項目 | 結果 |
|------|------|
| 回填量 | HN 2893 + Dev.to 2238 = **5131 篇**，涵蓋 2026-04-01 ~ 05-30 |
| 月份分布 | 4 月 1748 + 5 月 3370 |
| 每模型 | claude 2877 / gpt 2272 / gemini 453 / deepseek 241 / llama 135 / grok 109 |
| 冪等 | 重跑 DB 僅 +24（兩次執行間的真實新文），無重複暴增 |
| **F8 重跑** | discussion_spike **11→25 筆**，相對真實 baseline：**Claude 5/13 118 篇 vs 平日中位 60.5（severity 7.76）**、DeepSeek 5/13 39 vs 4（severity 10）等 |

**Code review（第八輪，最嚴）**：採納全部 2 HIGH + 3 MEDIUM：
1. ✅ `_numeric_filters` tz-safe（naive datetime 不再產生 8 小時偏移）。
2. ✅ 補 `_batch` 不變式測試（chunk×欄位 < 32767，鎖住三表）+ chunk 跨界整合測試。
3. ✅ Dev.to `since` 提前停止測試（page_all_older）。
4. ✅ 文件化 Algolia ~1000/查詢上限（需更完整要切子區間）。
5. ✅ `crawl_devto` 加 `until`，與 HN 對稱（不再 client-side 過濾）。

**測試**：API 30 + ML 15 + workers 46 = **91 passed**，ruff 全綠。
**DB 現況**：posts **5142** + release_events 198 + events（spike 25 + launch 92）。

---

## 階段 13：6 模型即時看板接真實數據 ✅（首頁第三段）

**目標**：把首頁「6 模型即時看板」從假卡片改成真實彙總。

- `api/services/models.py`：`get_model_dashboard` —— 三個彙總查詢（貼文總數+近7天用 `count() FILTER`、發布數+最新時間、近7天突增最大 severity），以 model_id 在 Python 合併（無資料模型也出現、補 0）。
- `api/routers/models.py`：`GET /api/models`（第 3 個業務 endpoint，F2）。
- 前端：`lib/types.ts` ModelSummary、`getModelDashboard`、`components/model-card.tsx`（突增亮黃點，`spike_severity != null` 正確保留 severity 0）、`page.tsx` Promise.all 改 3 個並行。

**端到端驗證**：`/api/models` 實機回 6 模型真實數字（claude 2893/近7天566/spike10、gpt 2282/246、gemini 456/spike5.4…）；首頁 HTML 渲染 `2,893`/`2,282`/「近7天」。typecheck/lint/build 全過。

**Code review（第九輪）**：評「正確、idiomatic，無 Critical/High」。採納 must-fix：
1. ✅ 補測試：**無資料模型出現且全 0/None**（核心不變式）、releases 彙總、spike 彙總。
2. ✅ 清掉 main.py 過時 TODO 註解。
> 已記錄待辦（非阻塞）：4 個整合測試檔的 engine/session fixture 可抽 conftest.py；endpoint 可加 Pydantic response_model；events 可加 (event_type,occurred_at) 複合索引。

**測試**：API 34 + ML 15 + workers 46 = **95 passed**，ruff 全綠。

**現況**：首頁三段全部真實資料 —— 事件流（F8）+ 最新發布 + **6 模型看板**。後端 3 個業務 endpoint。

---

## 階段 14：前端優化成業界級 ✅（簡潔明瞭 · Linear/Vercel 風）

**目標**：把陽春前端升級成業界級、簡潔明瞭的暗色儀表板。先派設計 agent 出具體 spec，再實作。

**做了什麼**
- **字型**：`next/font` 載入 Inter + JetBrains Mono（CSS 變數接 Tailwind）；中文走系統 CJK fallback。修掉原本 fontFamily 指 Inter 卻沒載入的問題。
- **版面**：置頂 sticky header（wordmark + 標語 + LIVE 脈動點）、`max-w-5xl` 置中、`space-y-12` 節奏；去除 emoji 標題、改克制的 mono 小標。
- **設計系統**：CVA `Badge` chip（模型=紫/版本=青/突增=琥珀/中性）、`.card`/`.card-interactive`、單一強調色原則。
- **元件重構**：event/release/model 卡片改 Inter 標題 + Badge + stat 數字（`tabular-nums` + 綠色 delta + 突增亮點）。
- **載入**：每區塊獨立 async + `<Suspense>` 串流 + 骨架（header 立刻顯示）。
- **a11y**：focus-visible ring（限互動元素）、aria-hidden 裝飾、reduced-motion、對比度提升（白字透明度 /40~/60 達 WCAG AA）。
- **RWD**：手機 1 欄、看板 2 欄；桌機 events 2 欄、看板 6 欄。
- 移除未用的 recharts 依賴。

**驗證**：typecheck/lint/build 全過；**用 Playwright 實截桌機 + 手機圖**確認視覺（乾淨、層次清楚、真實數據）。

**Code review（第十輪）**：評「solid, ship-ready，無 Critical/High」。採納 polish：移除 recharts、
ReleaseCard 加 aria-label、footer 對比度、focus-visible 限定互動元素、LiveDot aria-hidden、
relativeTime formatter 提到模組層、字型加 Noto Sans TC fallback。

**現況**：前端達業界級（簡潔暗色儀表板）。後端 3 業務 endpoint、前端三段真實資料 + Suspense 串流。

---

## 階段 15：產品化（讓人一看就懂）+ 問題全紀錄 ✅

**背景**：使用者反饋「看不大懂在做什麼」。派 2 個研究 agent 調查市面產品（TLDR AI、Brand24、Exploding Topics、Stripe、Vercel、PostHog…），套用「自我解釋」設計。

**做了什麼（前端，無需改後端的部分）**
- **Hero**：價值主張「AI 模型的即時動態，一眼掌握」+ 它在做什麼 + 範圍（5 秒看懂）。
- **近 7 天摘要列**：突增 / 新發布 / 升溫中（先給答案；三格統一 7 天窗口）。
- **每段「這是什麼」說明**、空狀態改「一切平靜」框架、技術詞→人話（近7天/vs 平日/tooltip）。
- **突增白話化**：不秀 z-score，改「約為平常 N×」+ 文字標籤（升溫/熱議/爆量）。

**做了什麼（後端，加產品價值）**
- **突增「主因」**：偵測時存當天最熱門貼文標題 → 卡片顯示「主要討論：〈標題〉」（Brand24 的 "this spike was caused by X"）。
- **對帳刪除殭屍事件**：回填後不再成立的舊突增（如 claude 05-28，舊 median=1.5）會被刪除 —— 同時解決「主因空白」與資料誤導。

**問題全紀錄**：新增 [`docs/progress/issues-log.md`](issues-log.md) —— 整個開發過程的**所有問題**（環境/網路/DB/CI/邏輯，22 項）：症狀→根因→解法→檔案。

**驗證**：typecheck/lint/ruff 全過；Playwright 截圖確認 hero/摘要/主因都正確顯示。
**Code review（第十一輪）**：抓到資料誠實度問題（摘要窗口、median=0、殭屍事件）全修。

---

## 階段 16：情緒分析（Week 4，與 HN 的核心差異化）+ 30 篇論文 ✅

**目標**：實作情緒分析 —— HN 只有讚數，這裡給情緒/口碑/翻轉，是與 HN 最大的差異化。

**實作（`ml/ml/sentiment.py`，production-ready）**
- `SentimentAnalyzer`（RoBERTa `cardiffnlp/twitter-roberta-base-sentiment-latest`）：analyze / analyze_batch（溫度校準 + 信心棄答帶）、summarize（口碑指數 + 分歧度）、detect_flip（口碑翻轉）。
- **truststore**：模組頂層 `inject_into_ssl()` → 在 TLS 攔截網路下也能下載模型。
- 錯誤處理：torch/transformers 缺、模型載入失敗、文本 truncate、GPU/CPU 自動、**label 驗證守衛**。

**研究 30+ 篇論文並整合**（兩個研究 agent；清單見 [`docs/research/sentiment-literature.md`](../research/sentiment-literature.md)）。已整合的文獻技術：
- 溫度縮放（Guo 2017）、信心棄答帶（Xin 2021）、信心加權 soft 聚合（Dawid-Skene 1979 / PLOS 2024）、
  小樣本收縮（Brown 2001）、**兩比例 z 檢定判翻轉**、極化分數（Morales 2015）、反諷標記（Joshi 2017）。

**實測（你的 RTX 4060, device=cuda）**
- 單則：DeepSeek 早期 positive 0.97/0.92，近期 negative 0.91。
- 風向：早期口碑 **+59**（信心加權+收縮，比天真 +100 保守）、近期 **-55**，分歧度 0。
- 翻轉：⚠️ 偵測到（**z=3.16, p=0.002** 統計顯著）：口碑 +59 → -55。

**環境發現**：使用者系統 Python 已有 **GPU torch (cu126) + transformers**（其研究環境）→ 直接複用、不重裝。
**Code review（第十二輪）**：抓到 label 脆弱性（High）等，已修。測試 ML sentiment 12 + 其餘 = 全綠。

> 後續：把情緒批次跑進 DB（sentiments 表）+ 模型卡顯示口碑 + sentiment_flip 事件（解鎖第三種偵測）。

---

## 階段 17：情緒接進產品（口碑落地到畫面）✅

**目標**：把情緒從 demo 變成產品 —— 批次跑 5000 篇 → DB → 模型卡顯示口碑 → sentiment_flip 事件。

- `sentiments` 表（post_id PK、label、三類機率、confident）+ migration `32a6a15ed0d2`。
- `scripts/backfill_sentiments.py`：**GPU 批次跑 5142 篇**（device=cuda），增量（只跑未分析的）。
- `api/services/models.py`：口碑指數 = 信心加權 soft（p_pos-p_neg）+ 小樣本收縮，加進 `/api/models`。
- 前端 `model-card.tsx`：顯示「口碑 +13 ↑」（依正負上色）。
- `run_event_detection.py`：**sentiment_flip 偵測**（近 14 天 vs 前 14 天，detect_flip 兩比例 z 檢定）+ 對帳；endpoint Literal + 前端 FlipCard 補完。

**端到端實測**
| 項目 | 結果 |
|------|------|
| GPU 情緒批次 | ✅ 5142 篇（499↑ / 4006 中 / 637↓） |
| 各模型口碑 | deepseek **+13** · gemini/gpt +7 · llama +6 · claude/grok +3 |
| 模型卡顯示 | ✅ 截圖確認「口碑 +13」等渲染出來 |
| sentiment_flip | 0 筆（真實資料口碑都小幅正面、無劇烈翻轉 —— 誠實；能力已實作+測試）|

**環境**：複用使用者系統 Python 的 GPU torch；DB 套件（sqlalchemy/asyncpg）裝進系統 Python 供 GPU 批次。
**測試**：API 35 + ML 27 = 62（+口碑聚合、flip）全綠。

> 差異化落地：HN 只有讚數，Pulse 模型卡現在顯示**口碑指數**（真實資料），且具備口碑翻轉偵測能力。

---

## 階段 18：決策報告 /decide（F3/F4，資料驅動）✅

**目標**：「Claude 還是 GPT 適合做 X?」—— 用真實討論數據給有證據的選型建議（HN 做不到）。

**設計**：**資料驅動**而非 LLM 包裝 —— 答案基於 Pulse 真實資料（口碑、討論量、議題相關熱門討論），
**無需 key 即可運作**；LLM 只是選配的自然語言合成層（有 `ANTHROPIC_API_KEY` 才啟用，已寫好休眠中）。

- `api/services/decide.py`：`compare_models`（複用 dashboard + 議題過濾的熱門討論 + 資料驅動推薦 `_recommend`）。
- `api/routers/decide.py`：`GET /api/decide?models=a,b&topic=...`（支援 checkbox 重複參數）。
- 前端 `app/decide/page.tsx`：原生 GET form（模型 checkbox + 議題）+ 推薦 banner + 各模型比較（口碑、議題相關真實討論）。header 加「決策」導覽。

**端到端實測**（截圖確認）：比較 Claude/GPT/DeepSeek + 議題「coding agent」→ 推薦 **DeepSeek（口碑 +13）**，
並列出各模型真實的 coding-agent 討論（Claude「Superset – IDE for the agents」、DeepSeek「native coding agent low cost」）。

**測試**：API 40（+decide 純邏輯 5）全綠，ruff 全過。使用者將於功能更完整時提供 Anthropic key 啟用 LLM 合成。

---

## 階段 19：Threads 爬蟲（Selenium，best-effort plugin）✅

**背景**：使用者要用 Selenium 爬 Threads（Meta）。我先說明限制（登入牆、反爬、selector 易變、不適合 24/7），做成獨立選配 plugin。

- `workers/crawlers/threads.py`：純函式 `normalize_thread_post`（可測）+ `crawl_threads` 產生器
  （Selenium headless Chrome、捲動 lazy load、保守 selector + 大量 try/except 優雅降級、`asyncio.to_thread` 包同步呼叫）。
- selenium 加進 workers 依賴；6 個純解析測試。

**實測（意外可跑）**：Selenium Manager 自動下載 driver、Chrome 啟動、**未登入也抓到 ~10 則提到 Claude/GPT 的真實 Threads 貼文**。
- 限制：未登入只看到部分公開貼文；selector 會抓到作者 header 雜訊（內文都在、models 正確命中）→ 已加長度過濾降噪，Week 3 DQC 會再清。
- **未灌進正式 DB**（避免 noisy 資料污染）；作為 plugin 交付，selector/去雜訊/登入 cookie 之後可微調。

**測試**：workers 52（+threads 6）全綠，ruff 全過。

> 定位：主力仍是免 key 的 API 來源（HN/Dev.to/HF/GitHub）；Threads/Selenium 是「某來源無 API 時的選配手段」。

---

## 階段 20：Airflow 排程化（5 DAG，TaskFlow + Datasets + ExternalPython）✅

**背景**：使用者要把手動腳本（crawl / fetch_releases / event_detection）排程化（先研究再進行）。
派 2 個研究 agent（基礎建設 + DAG 設計）調查 Airflow 2.9 best practice，再實作 → 端到端驗收。

**共用 pipeline 套件（DRY 核心）**：把「抓 → UPSERT」「事件偵測」收斂到 `workers/pipeline/`，
scripts 與 DAG 共用同一份 async 編排（單一真實來源）。`run_event_detection.py` 改薄包裝（行為逐位元一致）。
- `pipeline/crawl.py`：`crawl_hackernews_to_db` / `crawl_devto_to_db` / `crawl_lobsters_to_db` /
  `crawl_reddit_to_db`（缺 key 自我偵測、不算失敗）/ `fetch_releases_to_db`；模組頂層注入 truststore。
- `pipeline/events.py`：`run_event_detection()`（spike + launch + flip + 對帳刪除，同一交易）。

**5 個 DAG（TaskFlow `@dag/@task`）**：
- `crawl_hackernews`（*/15）、`crawl_community`（devto+lobsters，*/15 錯開）、`crawl_reddit`（*/15，預設 paused）
  → producer：成功標記 **POSTS** Dataset。
- `fetch_releases`（@hourly）→ 標記 **RELEASE_EVENTS** Dataset。
- `event_detection`：**資料感知排程** `DatasetOrTimeSchedule([POSTS, RELEASE_EVENTS] + 每日 01:00 安全網)`
  —— 有新資料才觸發、不空轉。
- `default_args`：retries=3 + 指數退避（max 30m）+ Slack `on_failure_callback`（Variable，best-effort）。
- `catchup=False`、`max_active_runs=1`、固定 `start_date`（避免回填風暴）。

**關鍵架構決策（依賴衝突）**：apache-airflow 2.9 把 **SQLAlchemy 鎖 <2.0**，但業務碼
（`DeclarativeBase`/`mapped_column`/`async_sessionmaker`）需 **SQLAlchemy 2.0** → 無法共存於同一直譯器。
解法：自建 image 內**雙環境** —— 主環境跑 Airflow（1.4）；獨立 venv `/opt/airflow/pulse-venv`
裝 SQLAlchemy 2.0 + 爬蟲/DB 依賴；DAG task 用 **`@task.external_python`** 在該 venv 執行業務邏輯。
**刻意不裝 torch**（情緒分析留本機 GPU 腳本，見 [方向討論]）。原始碼 bind-mount + PYTHONPATH，改 DAG/爬蟲免重 build。

**端到端實測（docker compose 起 Airflow，業務 DB=容器 `db:5432`）**：
- 5 DAG 全部註冊、**0 import error**；webserver `/health` HTTP 200（:8080）。
- `airflow tasks test event_detection` → `{spike 25, launch 92, flip 0, upserted 117}`（與本機跑**完全一致**）。
- `airflow tasks test crawl_hackernews` → **250 筆 upserted**；`crawl_community/devto` → **110 筆**。
- 證 ExternalPython venv（SQLAlchemy 2.0）→ asyncpg → 容器 DB 全鏈路打通；重抓多為既有資料
  （冪等去重，posts 5142→5149 僅淨增 7，符合預期）。

> 亮點：不只「跑 cron」—— **Datasets 資料感知排程** 串 producer→consumer、
> **ExternalPythonOperator 解 SQLAlchemy 版本衝突**、冪等 upsert 保證 retry 安全，是可寫進履歷的 MLOps 工程。

---

## 階段 21：DQC 資料品質過濾（評分 + 跨來源去重）✅

**背景**：使用者要做資料品質過濾（範圍：垃圾/廣告/SEO、相關性評分、跨來源去重；**不做語言過濾**）。
先派 2 個研究 agent（品質/相關性評分 + 跨來源去重），再實作 → 端到端 → code review → 修。

**純函式核心（ml/，無 DB/網路、可測；不用 LLM —— 啟發式更快/可解釋/適合排程）**
- `ml/data_quality.py`：`score_post(post, models) -> (quality_score 0-100, flags)`。依 ADR-009 扣分制
  （score=clamp(100+Σ扣分)、DELETED 歸零），**移除語言層**。flag：TOO_SHORT/LINK_HEAVY/EMOJI_SPAM/
  ALL_CAPS/EXCESSIVE_PUNCT/SPAM_PHRASE/AD/SEO/AFFILIATE/CLICKBAIT/JOB_POSTING/LIKELY_BOT/
  KEYWORD_NOT_IN_BODY/WEAK_KEYWORD/SARCASM_DETECTED。先 HTML 解碼+去標籤、SEO 用**密度**判定且排除模型別名。
- `ml/dedup.py`：跨來源近似重複 —— `canonicalize_url`（去追蹤參數/www/fragment）+ `normalize_title` +
  `simhash64` 4×16-bit 分桶 + token `jaccard` 雙門檻 + union-find 分群；`select_canonical`（最早發佈優先）；
  `reconcile_dedup_flags`（冪等增刪 DUPLICATE/CANONICAL:<id>，保留品質 flag）。

**編排 + DAG**
- `workers/pipeline/quality.py`：`process_quality`（挑未處理、評分、Core executemany 分塊寫回）+
  `detect_duplicates`（全表分群、對帳更新去重 flag）+ `run_dqc`（分批評分到乾淨再去重）。
- `workers/dags/data_quality_dag.py`：第 6 個 DAG，資料感知排程（POSTS + 每日 02:00），產出 **POSTS_DQ_PASSED** Dataset。
- `scripts/run_dqc.py` 手動薄包裝。

**端到端實測（5149 篇真實資料）**
| 項目 | 結果 |
|------|------|
| 品質分布 | **高(≥60) 5065 / 中 81 / 低(<30) 3**（98.4% 高品質，低分都是 Ramp 廣告等真垃圾）|
| 主要 flag | WEAK_KEYWORD 660（提到但非主題）、SPAM_PHRASE 51、SEO 45、TOO_SHORT 42、AD 28… |
| 跨來源去重 | **247 群 / 347 篇**標記重複（如「Google 投資 Anthropic $40B」HN 多篇 → 同 canonical）|
| 冪等 | 重跑 process 0 篇、去重穩定 347（無重複標記）|
| Airflow | data_quality DAG 經 external_python venv 跑通：`{clusters 247, duplicates 347}` |

**Code review（C1+H1+H2 已修）**：
1. ✅ **C1**：`run_dqc` 50k 上限會靜默漏處理 → 改 while 收斂 + 觸頂記 warning。
2. ✅ **H1**（使用者最在意的誤判）：裸 `hiring`/數字清單/單一推廣詞/`sign up` 等誤殺正當貼文
   → JOB 去裸 hiring、CLICKBAIT 去數字清單、SPAM 需 ≥2 推廣訊號、移除 "sign up"。低分從 32→3。
3. ✅ **H2**：AD 扣分 40→30（降低與 SPAM_PHRASE 疊加的過重懲罰）。
4. 加 H1 回歸測試（正當貼文須維持 ≥60）+ 去重覆蓋（來源優先序、union-find 遞移）。

**過程踩坑（見 issues-log G）**：HN 內文的 HTML 實體 `&#x27;` 被 hashtag regex 當 `#x27` → 637 篇誤判 SEO
（解碼+去標籤修掉）；SQLAlchemy ORM bulk update 報錯 → 改 Core `update(table)` executemany。

**測試**：ml 64（+data_quality 19 + dedup 18）全綠，ruff 全過。

> 註：DQC 產出 quality_score/flags 與 POSTS_DQ_PASSED Dataset，**下游過濾為 opt-in**（下一步可讓事件偵測/
> 看板只看 ≥60 的貼文）—— 不在此階段悄悄改既有數字，留給使用者定門檻。

---

## 階段 22：X/Twitter 爬蟲（best-effort 選配，twscrape + cookie）✅

**背景**：使用者要加 Twitter/X 來源。先研究 2026 現況 → **無免費官方 API**（官方收費、Nitter 多半失效、
search 需登入、snscrape 失效）→ 唯一可行是非官方 client。選 **twscrape**（2026 最活躍維護）以帳號 cookie 讀公開推文。

- `workers/crawlers/twitter.py`：純函式 `normalize_tweet`（twscrape `tw.dict()` → 共用 upsert 形狀，
  score=讚+轉推）+ `crawl_twitter` 產生器（缺 cookie/未裝 twscrape/查詢失敗 → 記 log、不 crash）。
  帳號池 SQLite 固定路徑、刪舊重建避免 inactive 卡住。
- `pipeline/crawl.py` 加 `crawl_twitter_to_db`（讀 settings.x_*，缺 cookie 回零統計，與 reddit 一致）。
- `crawl_x` DAG（第 7 個，預設 **paused**、每 30 分鐘錯開）；config 加 `x_auth_token/x_ct0/x_username`；
  twscrape 加進 workers 依賴 + Airflow venv image。

**定位**：與 Threads 同 —— **選配 best-effort 補充來源**，預設關閉（無 cookie 即 no-op），主力仍是免 key API。
違反 X ToS、低量風險小但非零 → 建議用次要帳號。等使用者貼 cookie + unpause + 重 build image 即可live。

**Code review（sonnet，已修）**：帳號池路徑固定化 + 刪舊重建（避免 stale inactive 帳號卡住密碼登入）、
score 納入轉推、id_str 後備註解澄清、docstring 排程修正。

**測試**：workers 61（+twitter 純函式 9）全綠，ruff 全過；crawl_x DAG 註冊、0 import error（paused）。

---

## 階段 23：前端可用性大升級（自我解釋 + 模型詳細頁 + 趨勢圖）✅

**背景**：使用者反饋「不大清楚到底要怎麼用」。開**背景 agent（worktree 隔離）平行處理**：研究同類產品 →
稽核現有前端 → 重設計 → 實作 → 驗證。聚焦「讓冷啟動使用者一眼看懂這是什麼、怎麼用」。

**做了什麼**
- **新 Hero**：一句話價值主張 + 明確列出與 HackerNews 的差異 + 三張能力卡。
- **「三步上手」引導條**（首訪顯示、localStorage 記憶）+ 術語人話化 + `InfoHint`（滑過才看真實指標，去掉 z-score 等黑話）。
- **事件流篩選器**（依事件類型/模型，狀態存 URL、可分享、上一頁有效）+ **導覽列**（儀表板/決策報告，當前頁高亮）。
- **模型詳細頁 `/models/[slug]`**：點模型卡 → 趨勢圖（每日討論量 + 口碑走勢，**純 SVG 零依賴**）、近期事件、熱門討論、最新發布、loading/not-found。
- 解釋性空/錯狀態（「有變化時這裡會自動冒出卡片…」）。

**新後端 API**：`GET /api/models/{slug}?trend_days=`（時間序列：每日討論量 + 口碑，gap-filled；複用 dashboard 口碑公式保持一致）+ `services/model_detail.py` + 整合測試。

**端到端實測（合併進 main 後）**：`/api/models/claude` HTTP 200（口碑 3、31 個趨勢點、5 熱門討論）；
首頁新版 + `/models/claude` 詳細頁在 :3000 渲染成功。typecheck/lint/build 全過、`npm ci` 可重現、**後端掛掉前端不崩**（fail-soft）。
**零新增 npm 套件**（圖表手刻 SVG），順手清掉舊 `@emnapi` 跨平台 lockfile 風險。

> 工法亮點：用**獨立 worktree 背景 agent 平行開發**，與後端（X 爬蟲）同時推進、互不干擾，完成後乾淨合併（無衝突）。
> 產品意義：從「能跑但看不懂」→「自我解釋、可操作」。
