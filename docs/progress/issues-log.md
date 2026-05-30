# 開發問題全紀錄（踩坑 & 解法）

> 開發 Pulse 過程中遇到的**所有問題**：症狀 → 根因 → 解法 → 影響檔案。
> 給未來的自己、其他工程師，也是技術 blog 的素材（PROJECT_PLAN 的 Blog 2/3）。
> 分類：環境/平台、網路/TLS、資料庫、CI/CD、程式邏輯（code review 抓到）。

---

## A. 環境 / 平台（Windows）

### A1. 本機 PostgreSQL 18 佔用 5432，與 Docker DB 衝突
- **症狀**：`docker compose up -d db` 後，連線 `localhost:5432` 報 `password authentication failed for user "pulse"`；容器內 `psql` 卻正常。
- **根因**：本機已裝 PostgreSQL 18 服務佔 IPv4 `0.0.0.0:5432`，Docker proxy 只搶到 IPv6 `[::]:5432`；`localhost` 在 Windows 先解析 IPv6/IPv4 不定 → 連到錯的 DB。
- **解法**：docker host 埠改 **5433**（容器內仍 5432）、連線字串用 **127.0.0.1**（強制 IPv4）。
- **檔案**：`docker-compose.yml`、`.env.example`、`api/api/config.py`

### A2. Windows cp950 讀取 alembic.ini → UnicodeDecodeError
- **症狀**：`alembic revision` 報 `'cp950' codec can't decode byte ... illegal multibyte sequence`。
- **根因**：configparser 用 OS locale 編碼（zh-TW Windows = cp950）讀 `.ini`，但檔案是 UTF-8 且含中文註解。
- **解法**：`alembic.ini` 保持 **ASCII-only**（`.py` 不受影響，Python 預設 UTF-8 讀原始碼）。
- **檔案**：`api/alembic.ini`

### A3. Windows console cp950 印中文 / emoji → crash
- **症狀**：腳本 `print("✅ ...")` 報 `UnicodeEncodeError: 'cp950' codec can't encode character '✅'`。
- **根因**：Windows console 預設 cp950，無法輸出 emoji / 部分中文。
- **解法**：腳本開頭 `sys.stdout.reconfigure(encoding="utf-8")`（win32 限定）。
- **檔案**：`scripts/*.py`

---

## B. 網路 / TLS（企業/校園憑證攔截）

> 共同根因：所在網路做 TLS 攔截，注入的根憑證在 **OS 信任庫**但不在各語言工具的信任庫 → `CERTIFICATE_VERIFY_FAILED`。

### B1. pip 裝不了套件
- **症狀**：`pip install` 報 `SSLError ... CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`。
- **解法**：`pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org ...`

### B2. httpx / 爬蟲連外 SSL 失敗
- **症狀**：`crawl_hackernews` 等對外 https 報 `httpx.ConnectError: CERTIFICATE_VERIFY_FAILED`（爬蟲優雅回 0 筆、不 crash）。
- **解法**：`truststore.inject_into_ssl()` 讓 Python 改用 **OS 信任庫**（無攔截的網路也安全）。
- **檔案**：`workers` 依賴 + `scripts/test_crawl.py` / `fetch_releases.py` / `backfill.py`（best-effort import）

### B3. npm 裝不了 / next/font 抓不到字型
- **症狀**：`npm install`、`next build`（next/font 抓 Google Fonts）SSL 失敗。
- **解法**：`NODE_OPTIONS=--use-system-ca`（Node 22+ 用 OS 信任庫，等同 Python truststore）。

### B4. Docker build 內 pip SSL 失敗
- **症狀**：`docker compose build` 的 `RUN pip install` 報 `CERTIFICATE_VERIFY_FAILED`（build 容器無 OS 信任庫的攔截根 CA）。
- **解法**：`pip install --trusted-host pypi.org --trusted-host files.pythonhosted.org --trusted-host pypi.python.org ...`（同 B1，但在 Dockerfile 內）。
- **檔案**：`workers/Dockerfile.airflow`

### B5. 容器內爬蟲對外 HTTPS 失敗（攔截 CA 不在 Linux 容器）
- **症狀**：Airflow 容器內 `crawl_hackernews` 等對外 https 仍 `CERTIFICATE_VERIFY_FAILED`，即使裝了 truststore。
- **根因**：攔截 proxy 的根 CA 在 **Windows host 信任庫**，但 **Linux 容器**的信任庫沒有 → 容器內 truststore 讀的是容器自己的 store，救不了。
- **解法**：把 host 信任庫匯出成 `.crt` 放 `workers/ca-certs/`，`Dockerfile.airflow` 併進 `/etc/ssl/certs/ca-certificates.crt`；空目錄（正常網路）為 no-op。`.crt` 入 `.gitignore`（機器相關、勿入庫）。
- **檔案**：`workers/Dockerfile.airflow`、`workers/ca-certs/README.md`、`.gitignore`

---

## C. 資料庫 / SQLAlchemy / Alembic

### C1. PostgreSQL 32767 bind 參數上限（回填 5000+ 列爆掉）
- **症狀**：回填時 asyncpg 報 `the number of query arguments cannot exceed 32767`。
- **根因**：`upsert_posts` 把 5000+ 列塞進一條 INSERT；13 欄 × 5000 列遠超上限。
- **解法**：抽 `api/services/_batch.py` 的 `chunked()`，三個 upsert 服務全部分塊（單一交易末尾才 commit，保原子性）。加靜態不變式測試（chunk×欄位 < 32767）。
- **檔案**：`api/services/_batch.py`、`posts.py`、`releases.py`、`events.py`、`tests/test_batch_invariants.py`

### C2. pytest-asyncio 跨 event loop
- **症狀**：整合測試報 `asyncpg ... another operation is in progress`。
- **根因**：module-scope 的 async engine fixture 建在某 loop，但 pytest-asyncio 每個 test function 各自開新 loop → 跨 loop 用同一連線。
- **解法**：`engine` fixture 改 **function scope**（與 test 同 loop）。
- **檔案**：`api/tests/test_*_integration.py`

### C3. alembic autogenerate 偵測不到表 / server_default 漏改
- **根因**：`env.py` 沒 import models；缺 `compare_server_default`。
- **解法**：`env.py` `import api.models` + 加 `compare_server_default=True`。
- **檔案**：`api/alembic/env.py`

### C4. alembic post-write hook（ruff）找不到 entrypoint
- **症狀**：產 migration 後 `Could not find entrypoint console_scripts.ruff`。
- **解法**：hook 改 **exec 模式**（跑 PATH 上的 ruff），並加 `ruff check --fix` 讓產出的 migration 不會壞 CI。
- **檔案**：`api/alembic.ini`

---

## D. CI/CD（GitHub Actions）

> 初始 commit 起 CI 就一路紅，根因逐一修。本機 ≠ CI（Windows vs Linux、npm 11 vs CI npm）是反覆踩雷主因。

### D1. API job exit 2 —— `uv run ruff/pytest` 找不到
- **根因**：CI 的 `uv sync` **不裝** optional dev 依賴（ruff/pytest 在 `[dev]`）。
- **解法**：`uv sync --extra dev`。
- **檔案**：`.github/workflows/ci.yml`

### D2. ruff import 排序（api 視為 first-party）
- **根因**：在 `api/` 內跑 `ruff check .` 把 `api` 當 first-party，import 排序規則與我先前用絕對路徑跑時不同。
- **解法**：一律在 `api/` 目錄內 `ruff check --fix .`（與 CI 一致）。

### D3. ruff B008 —— FastAPI `Depends()` 在參數預設
- **根因**：`Depends(get_db)` 放參數預設是 FastAPI 慣例，但觸發 bugbear B008。
- **解法**：pyproject 加 `[tool.ruff.lint.flake8-bugbear] extend-immutable-calls = ["fastapi.Depends", ...]`。

### D4. Web job —— 缺 ESLint 設定檔
- **根因**：`web/` 無 `.eslintrc`，`next lint` 在 CI 非互動模式找不到 config 直接失敗。
- **解法**：加 `web/.eslintrc.json`（extends `next/core-web-vitals`）。

### D5. Web job —— 缺 package-lock.json（npm ci 必敗）
- **解法**：本機 `npm install` 生成 lock（搭 `--use-system-ca` 過 SSL），改回 `npm ci` + 快取。

### D6. Web job —— npm ci EUSAGE：lock 缺 @emnapi（跨平台）
- **症狀**：CI `npm ci` 報 `package.json and package-lock.json ... in sync. Missing: @emnapi/core ... from lock file`。
- **根因**：在 **Windows** 跑 `npm uninstall recharts` 把 lock 裡 **Linux 需要的 optional 依賴**（@emnapi/*）剪掉了；本機 npm ci 反而過（Windows 不需要那些）。
- **解法**：刪 lock 重新完整 `npm install` 重生（含所有平台 optional 依賴）。
- **教訓**：跨平台（Windows 開發 / Linux CI）下，動 lock 後要確認 optional 依賴完整。

---

## E. 程式邏輯（code review / 實測抓到）

### E1. `str(None)` → 字串 `"None"` 騙過必填防護
- **症狀**：缺 id 的貼文 `external_id` 變成 `"None"`，通過 upsert 的 `is None` 必填檢查。
- **解法**：缺 id 時保留 `None`（devto + hackernews 同源 bug 一併修）。
- **檔案**：`workers/crawlers/devto.py`、`hackernews.py`

### E2. 偵測未刪除「不再成立」的舊事件（殭屍事件）
- **症狀**：回填後，某些 backfill 前偵測到的討論突增（如 claude 05-28，當時 `median=1.5`）一直留著；回填後 claude 平日約 60 篇、05-28 不再算突增，但舊事件沒被刪 → 「主因」空白、數字誤導。
- **根因**：`run_event_detection` 只 upsert、不刪除。
- **解法**：偵測時**對帳**：刪除這次 dedup_key 不在當前偵測集合內的 spike/launch 事件。
- **檔案**：`scripts/run_event_detection.py`

### E3. `_numeric_filters` 對 naive datetime 時區不安全
- **根因**：`int(since.timestamp())` 對 naive datetime 會用本機時區 → 8 小時偏移。
- **解法**：`_epoch()` 內 `dt.replace(tzinfo=dt.tzinfo or UTC)`（naive 視為 UTC）。
- **檔案**：`workers/crawlers/hackernews.py`

### E4. 摘要列窗口不一致（30 天 vs 7 天）
- **根因**：「近期突增」數來自全資料（~30 天），但「升溫中」是 7 天 → 並列誤導。
- **解法**：摘要三格統一「近 7 天」窗口。
- **檔案**：`web/components/today-summary.tsx`

### E5. median=0 遮蔽最強的突增
- **根因**：`multiple = count/median` 用 `median` 當 truthiness 守衛，median=0（平日幾乎無討論）時最強的突增反而顯示「明顯升高」泛泛之詞。
- **解法**：`median===0` 獨立分支，顯示「從幾乎無人討論 突然爆量」。
- **檔案**：`web/components/event-card.tsx`

---

## F. 編排 / Airflow（Week 5-7 排程化）

### F1. apache-airflow 2.9 鎖 SQLAlchemy <2.0，與業務碼的 2.0 衝突
- **症狀**：自建 Airflow image `pip install "apache-airflow==2.9.3" "sqlalchemy>=2.0.25"` 報 `ResolutionImpossible`。
- **根因**：Airflow 2.9 把 SQLAlchemy 鎖在 **1.4**，但 `api.models` 用 **SQLAlchemy 2.0** 專屬的 `DeclarativeBase`/`mapped_column`/`async_sessionmaker` → 不能同直譯器共存。
- **解法**：image 內**雙環境** —— 主環境裝 Airflow（1.4）；獨立 venv `/opt/airflow/pulse-venv` 裝 SQLAlchemy 2.0 + 爬蟲/DB 依賴；DAG task 用 **`@task.external_python`** 在該 venv 跑業務邏輯。
- **檔案**：`workers/Dockerfile.airflow`、`workers/dags/*_dag.py`、`workers/dags/_common.py`

### F2. compose 注入的 `PULSE_DATABASE_URL` 被 settings 忽略 + host 錯
- **症狀**：DAG 連業務 DB 連到 `127.0.0.1:5433`（容器內無此服務）→ 連線失敗。
- **根因**：`api.config.Settings` 無 `env_prefix`，讀的是 `DATABASE_URL` 不是 `PULSE_DATABASE_URL`；且預設 host 是 host-only 的 127.0.0.1。
- **解法**：compose 改注入 **`DATABASE_URL=postgresql+asyncpg://pulse:pulse@db/pulse`**（service 名 `db`、無前綴）。
- **檔案**：`docker-compose.yml`

### F3. truststore 注入不到 ExternalPython 子行程
- **症狀**：truststore plugin 在 Airflow 主環境注入了，但 venv 子行程的爬蟲仍 SSL 失敗。
- **根因**：plugin 注入只在主直譯器生效；`@task.external_python` 另開 venv 子行程。
- **解法**：在 **`pipeline/crawl.py` 模組頂層**注入 truststore（不論哪個直譯器 import 都生效）。
- **檔案**：`workers/pipeline/crawl.py`（另見 B5：容器信任庫還要併入攔截 CA）

### F4. SQLAlchemy echo 灌爆 Airflow task log
- **症狀**：DAG task log 每筆都印整串 SQL（`echo=True`）。
- **根因**：`engine` 的 `echo=settings.environment=="development"`，容器未設 → 預設 development。
- **解法**：compose 設 **`ENVIRONMENT=production`** 關掉 echo。
- **檔案**：`docker-compose.yml`

> 補充：`@task.external_python` 的 task log 會出現 `No module named 'pendulum'` /
> `No package metadata for apache-airflow` 的 traceback —— 那是 operator 在 venv 內探測 airflow 版本
> 的**非致命**訊息（`expect_airflow=False` 已處理），task 仍正常回傳。

---

## 通用教訓

1. **本機 ≠ CI**：Windows/Linux、cp950/UTF-8、npm 版本、optional 依賴 —— 跨平台差異是最多坑的地方。
2. **TLS 攔截**：企業/校園網路下，pip/npm/httpx 都要各自指向 OS 信任庫（`--trusted-host` / `--use-system-ca` / `truststore`）；**Docker 容器**還要把攔截根 CA 併進容器自己的信任庫（B4/B5）。
3. **資料形狀會變**：回填讓時間序列從稀疏變密集，舊的偵測結果要能「對帳更新」，不能只新增。
4. **code review 每階段做**：E 區的 bug 多半是獨立 review agent 抓到的，不是測試。
5. **依賴版本衝突要隔離**：Airflow（SQLAlchemy 1.4）與業務碼（2.0）共存的正解是 ExternalPythonOperator + 獨立 venv，而非硬湊版本（F1）。
