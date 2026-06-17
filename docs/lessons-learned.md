# 踩雷紀錄 / Lessons Learned

> 每次犯的錯、根因、教訓都記在這裡。新的往**最上面**加（日期遞減），格式：
> `### YYYY-MM-DD — 一句話標題` → **症狀** / **根因** / **教訓**。
> 目的是同樣的雷不要踩第二次；review/開發前可掃一遍。

---

## 2026-06-17

### 假完成 / 假綠：agent 說「測試過」但實際沒做到
- **症狀**：第一個「報紙版整合」agent 中途斷線，回報像完成、`pytest` 也綠，但實際渲染出來還是舊卡片版（`border-radius` 出現 45 次、報頭沒換）。
- **根因**：測試太鬆（只驗 `<title>` 等字串），沒驗「實際版型」；agent 斷線留下半成品。
- **教訓**：交付物要**看實際產物**（渲染截圖 / grep 關鍵特徵如 `border-radius` 次數），不能只看「測試綠」。被 [[ci-false-green-lesson]] 命中第二次。

### newsletter-designer agent 連兩次 infra socket 斷線
- **症狀**：同一類 agent（newsletter-designer）連續兩次 `socket connection closed` 死亡，留半成品。
- **根因**：基礎設施/網路不穩（非任務難度）。
- **教訓**：同一型 agent 反覆死就**換 agent 類型（改 general-purpose）或自己動手**，別硬重試同一條路；大改寫優先自己 Write 整檔以利掌控。

### created_at 視窗只修一半 → 產品各面向不一致
- **症狀**：把電子報「今日視窗」從 `posted_at` 改 `created_at` 讓 Threads 進得來，但 feed / 今日事件仍用 `posted_at`，導致「電子報有 Threads、網站沒有」。
- **根因**：同一個語意（近期視窗）的定義散在多個讀取點，只改了其中一處。
- **教訓**：跨多處的語意改動要**抽共用定義**（後來抽 `api/services/recency.py`）一次套用，別逐點打補丁（altitude）。

### 部署相對路徑 → 容器內端點永遠回空
- **症狀**：`/api/storylines`、`/api/events/today` 在非 repo 根 cwd（uvicorn/docker）啟動時永遠回 `[]`。
- **根因**：`settings.*_file` 預設相對路徑 `data/*.jsonl`，相對 process cwd 解析。
- **教訓**：產出檔/資源路徑預設要**相對程式位置的絕對路徑**（`Path(__file__).resolve().parents[N]`），別相對 cwd；容器再以 env 覆寫。

### per-source 量級差 → 主力來源被洗掉 / 或反過來洗版
- **症狀**：(a) 原始互動分數排序下，HN points 量級壓過 Threads 讚數 → Threads（主力來源）幾乎不出現；(b) 改 created_at 後 Threads 數量暴增又反過來灌爆 feed。
- **根因**：跨來源互動量級不可直接比較，且「資格（進不進池）」與「排序（排不排得上）」是兩個獨立問題。
- **教訓**：跨來源排序要 **per-source 正規化 + round-robin 平衡**（抽到 `ml/hotness.py` 共用）；「資格」與「排序」分開想。

### 小而易忽略的渲染 / 計數 bug（code review 抓到）
- 首字下沉 `text[0]` 對「以 `[n]` 開頭的摘要」會把 `[` 放大、吃掉引註 → 任何「切第一字元」的處理要小心邊界。
- `outerjoin` 多列（重跑分類沒清舊列）→ 同筆貼文重複 → 計數翻倍。**join 後要依主鍵去重**。
- 日期分桶用 DB session 時區、補零基準用 UTC → 差一天。**時區要一致（明確 UTC）**。
- 前端圖表只畫 5 類、後端有 6 類（含「其他」）→ 總數少算、其他為主的日子誤判空狀態。**前後端列舉要對齊**。
- `escape(x)[:N]` 先跳脫再截斷會切斷 HTML entity（`&amp;`→`&am`）。**先截斷再跳脫**。
- compose 有 `PULSE_EVENTS_FILE` 卻漏 `PULSE_STORYLINES_FILE`。**新增同類資源時檢查所有並列設定點**。
