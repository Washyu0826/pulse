# Sprint 4 — 硬化（Hardening）報告

> 分支：`sprint4-hardening`（已 commit，**尚未** push origin，待使用者同意）。
> 基準日：2026-06-13。脈絡與護欄見 [docs/optimization-prompt.md](../optimization-prompt.md)。

## 目標

本輪**不加功能**，把既有核心循環做到更穩、更安全、更可觀測、更可重現。
依「風險 × 對作品集說服力」排序：先做安全與正確性，再做資料流可觀測性與 ML 可重現性，
最後收後端品質、前端測試與文件。所有狀態以「誠實標示」為準——未實際交付的不升級。

## 四條平行工作流

### API（後端硬化）

- 啟動期金鑰 fail-fast 驗證（缺啟用功能所需 key 即報錯，不靜默降級）。
- 外部呼叫補 timeout：Anthropic client、Ollama 呼叫。
- CORS 收緊（限定 method / header，不再 `*`）。
- 健康檢查不外洩內部 exception 訊息（未知錯誤回通用 unhealthy）。
- `decide` topic 參數加 `max_length`，防昂貴子字串搜尋。
- 抽 `_sentiment_index` 共用 helper，消除 `models.py` / `model_detail.py` 重複情緒公式。
- 拆 151 行的 `model_detail`、單一模型直接查詢（不再取整盤再過濾）。
- 新 Alembic migration：`Post.source` + `Theme.confident` 加索引。
- `/metrics` 加 LIMIT + 60s 快取；統一品質閾值單一來源；補型別註記。
- `events_today` 檔案缺失時記 warning + 回報資料新鮮度。
- 新增錯誤回應（422/404）測試；脆弱計時測試去 flake（改顯式時間比較）。

### ML（管線可重現性）

- 閾值集中化並附依據（研究引用 / 調參理由）。
- 訓練腳本：checkpoint + load_best + 中斷續跑（resume-from-checkpoint）+ 完整 seeding（torch/numpy/random）+ 可讀 OOM / 中斷錯誤。
- `evaluate.py` Qwen few-shot 路徑改逐筆 async 容錯（單筆失敗不中斷整批）；VRAM 清理。
- 新增事件摘要端到端整合測試（標記 slow / 可 skip，鎖住真實 BGE-M3 + Ollama + mDeBERTa 路徑）。
- `distill.py` / `translate.py` 補 async mock 測試。
- 統計指標回歸測試：McNemar / ECE / Brier / BH-FDR 鎖定已知數值（golden values）。

### Web（前端品質與首次測試）

- 模型清單收斂為單一事實來源（原散落三處）。
- 移除未實作的 `darkMode` 宣告（依「不加功能」哲學，移除以免誤導）。
- 友善錯誤訊息在地化集中化；非關鍵失敗降級行為一致化。
- **首次前端測試覆蓋**：Vitest 7 檔 45 測試（lib 工具、feed-filter URL 生成、SVG 邊界、localStorage、API 錯誤在地化）。

### Infra（部署與監控）

- docker-compose secrets 改為從 `.env` fail-fast（移除 `admin:admin`、`pulse-dev-secret` 預設）。
- Prometheus scrape target 修正 8000 → 8010。
- statsd / prometheus / grafana / cadvisor 補 healthcheck。
- 新增 `monitoring/prometheus/alerts.yml`：DAG 失敗、scheduler 心跳消失、資料新鮮度。
- `check_dataflow.py` 加盤中 `--lag-only` 模式（不必等日終才發現斷流）。
- `daily_refresh.ps1` 彙總各步驟失敗並 exit 1。
- Threads 爬蟲：fallback selector + 零結果告警（不再無聲回 0 筆）。

## 驗證結果（全綠）

| 模組 | 指令 | 結果 |
|------|------|------|
| API | `ruff check` + `pytest` | ruff 通過；46 pass / 30 skip |
| ML | `ruff check` + `pytest` | ruff 通過；429 pass / 2 skip |
| workers | `ruff check` + `pytest` | ruff 通過；70 pass |
| web | `typecheck` + `lint` + `vitest` + `build` | 全通過；45 vitest；build 11 頁 |

（吃真實 DB / 重模型的測試在無資源時 skip，故有 skip 數。）

## 未做 / Follow-up

- **Alertmanager 路由**：`alerts.yml` 規則已定義，但告警接收端（Slack / Email 路由）尚未配置。
- **盤中 `--lag-only` 排程**：模式已可手動跑，尚未接進 Airflow 定時觸發。
- **mypy 未跑**：離線 TLS 環境下依賴解析受阻，本輪 API `mypy` 未執行（ruff 已過）。
- **LoRA 訓練仍待跑**：訓練可重現性（checkpoint / resume）已就緒，但 LoRA Qwen2.5-1.5B 摘要模型**尚未實際訓練**（受限資料 + 算力）。
- **重模型整合測試未實跑**：端到端整合測試已寫好並標記 slow，但接真實 BGE-M3 / Ollama / mDeBERTa 的整合尚未在本輪實跑。
- **push 待核可**：`sprint4-hardening` 分支與既有未 push commits 待使用者明確同意後才推 origin。
