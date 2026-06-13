# Sprint 4 後續：CI 失敗修正紀錄（2026-06-14）

> Sprint 4 merge 進 main 後，CI（GitHub Actions，乾淨環境 + Linux + 真 PostgreSQL）抓到 3 個 job 失敗。
> 三者本機驗證時都「假綠」——根因都是**本機環境比 CI 寬鬆**。記錄根因、修法與教訓。

## 失敗 1：API — `test_model_detail` 3 筆（SQLAlchemy join 無左側）

- **症狀**：`sqlalchemy.exc.InvalidRequestError: Don't know how to join to <Mapper Post>. Please use the .select_from() method...`
- **根因**：Sprint 4 新增的 `api/services/models.py::get_model_summary`（單模型直查）兩個聚合查詢，SELECT 只有 `func.count()/func.sum()`、**沒有任何實體欄位**，`.join(Post)` 無從推斷左側 FROM。對照可運作的 `get_model_dashboard` 是因為它 SELECT 了 `PostModel.model_id` 才隱含確定 FROM。
- **修法**：兩個查詢都加 `.select_from(PostModel)`。本機以「編譯查詢」驗證（join 錯誤發生在 SQLAlchemy 編譯期，免 DB 即可重現），兩查詢皆編譯出 `FROM post_models`。
- **為何本機假綠**：`test_model_detail` 是吃真實 DB 的測試，本機無 DB 時 **skip**（Sprint4 驗證顯示 46 passed / 30 skipped）；CI 有 Postgres service 才會跑到 → 暴露 bug。

## 失敗 2：Workers — 12 筆 async 測試（pytest-asyncio 未裝）

- **症狀**：`Failed: async def functions are not natively supported.` + `PytestUnknownMarkWarning: Unknown pytest.mark.asyncio`。
- **根因**：`.github/workflows/ci.yml` 的 workers job 安裝步驟為 `pip install pytest ruff httpx asyncpraw tenacity`——**漏裝 pytest-asyncio**。crawler 測試是 `async def` + `@pytest.mark.asyncio`，外掛沒載入就整批失敗。
- **修法**：workers install 補上 `pytest-asyncio`（與 api job 一致）。
- **為何本機假綠**：本機用 `.venv`（API 的環境，含 pytest-asyncio）跑 workers 測試 → 70 passed。CI 的 workers job 是**獨立精簡環境**，沒有 pytest-asyncio。教訓：**每個 CI job 的精簡環境必須各自帶齊測試外掛**，不能靠共用的本機 venv。

## 失敗 3：Web — `npm ci`（lockfile 跨平台 optional 相依歪斜）

- **症狀**：`npm ci can only install when package.json and package-lock.json are in sync. Missing: @emnapi/core@1.11.1, @emnapi/runtime@1.11.1 from lock file`。
- **根因**：Sprint 4 web agent 在 **Windows** 導入 Vitest 並重生 lockfile。`@napi-rs/wasm-runtime`（eslint resolver 的 `unrs-resolver` 在無原生 binding 平台的 wasm fallback）要 `@emnapi ^1.7.1`，但 Windows 生成的 lockfile 把解析版本釘成 **1.10.0**，Linux CI 解析 `^1.7.1` 卻要 **1.11.1** → 版本歪斜、`npm ci`（嚴格）報缺。經典 npm 跨平台 optional 相依不完整問題。
- **修法**：刪除 `package-lock.json` 後以 npm 11.6.1 完整重生，讓整棵相依樹一致釘版（@emnapi 為平台無關的 wasm，重生後對所有平台一致）。
- **為何本機假綠**：本機 `npm install`/`npm run build` 不走 `npm ci` 的嚴格鎖檔比對；且 Windows 解析時用本機原生 binding，不觸發 wasm fallback 的 @emnapi 路徑。

## 共同教訓

1. **CI 才是真相**：本機驗證寬鬆（DB skip、共用 venv、非嚴格 npm）。涉及 DB / 多環境 / lockfile 的改動，要嘛在 CI 等價環境驗證，要嘛預期 CI 才抓得到。
2. **DB 依賴測試**：Sprint 4 既然改了 `get_model_summary`，就該起本機 DB（`docker compose up db`）跑那幾個 integration 測試，而非接受 skip。
3. **CI job 環境自足**：每個 job 的精簡安裝清單要覆蓋該模組測試的全部外掛（pytest-asyncio 等）。
4. **lockfile 跨平台**：在 Windows 重生 lockfile 易裁掉他平台 optional 相依；`npm ci` 嚴格。重生後最好在 Linux/CI 驗證，或完整重生確保一致。
