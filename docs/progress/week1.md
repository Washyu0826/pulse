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
