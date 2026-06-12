# Pulse 前端現況體驗審計（01-audit）

> UIUX 研究 agent #1 — 2026-06-12。方法：逐檔讀 `web/` 全部頁面與元件 + 對照
> `docs/ux/positioning-c-ux.md` 驗收標準 + 實際起 dev server（埠 3001）觀察 API 不可用時的真實渲染
> + 直接核對後端 `api/` 契約。**未改任何程式碼。**
>
> 環境備註：審計時埠 3000 已有一個既有 Next 實例、埠 8010 有 python 監聽（但該行程對
> `/api/*` 與 `/` 均回 404，疑似非本專案 API 或設定不同）、埠 8000（前端預設）無人監聽。

---

## 1. 頁面 / 路由盤點

| 路由 | 檔案 | 用途 | 主要互動 | 進入方式 |
|------|------|------|----------|----------|
| `/` | `web/app/page.tsx` | 首頁：每日實用情報門面。Hero → 模型側欄(左) + 篩選列 + 主題計數摘要列 + 今日事件 + 5 主題 kanban(中) + 本週熱詞(右) | 模型 chip / 情緒·來源·時間下拉（寫 URL params）、卡片整卡外連原文、卡片右上 ♥ 收藏 | 預設入口 |
| `/favorites` | `web/app/favorites/page.tsx` + `components/favorites-list.tsx` | 我的最愛（localStorage）＋勾選→生成知識材料包（.md / sources.jsonl 下載、複製、預覽） | 全選/勾選、AI 蒸餾開關、生成、下載/複製 | 導覽「我的最愛」 |
| `/decide` | `web/app/decide/page.tsx` | 決策報告：勾模型＋議題關鍵字 → 資料驅動選型建議 | 原生 GET form（無 client JS） | 導覽「決策報告」 |
| `/models/[slug]` | `web/app/models/[slug]/page.tsx` | 模型詳情：指標卡、趨勢圖（SVG）、近期事件、熱門討論、最新發布 | 點外連；有 `loading.tsx` 骨架與 `not-found.tsx` | 首頁左側「依模型瀏覽」 |
| （錯誤層） | `web/app/error.tsx`、`global-error.tsx` | 路由級/全域錯誤邊界，重試 + 回首頁 | — | 例外觸發 |
| （SEO/PWA） | `manifest.ts`、`sitemap.ts`、`robots.ts`、`opengraph-image.tsx` | 安裝、地圖、分享卡 | — | — |

主要共用元件：`site-header/site-nav/site-footer/logo/live-dot`（外殼）、`feed-filter/feed-summary/theme-feed/feed-card`（情報主軸）、`today-events`（事件忠實摘要）、`model-rail/trending-panel`（側欄）、`favorite-button/favorites-list`（收藏）、`theme-meta/source-meta`（軸向中介資料）、`ui/{badge,skeleton,info-hint}`、`section/section-status`、`charts/trend-chart`。

**死碼（無任何頁面引用）**：`how-to-use.tsx`、`model-board.tsx`、`model-card.tsx`（僅被 model-board 用）、`today-summary.tsx`、`events-feed.tsx`、`events-filter.tsx`、`releases-feed.tsx`。

---

## 2. 發現清單

格式：**[編號] 位置 — 問題 — 嚴重度 — 建議修法**

### A. 功能正確性 / 前後端契約（最痛）

**[A1] 前後端「主題」契約脫鉤 — 高**
- 位置：`web/components/theme-meta.tsx:22`（前端 5 主題：新工具/模型動態/使用方法/風險限制/倫理法規）vs `api/api/services/feed.py:22`（後端 `ACTIONABLE_THEMES = ("新工具", "使用方法", "邊界")`）、`api/api/routers/feed.py:21`（`Theme` Literal 也是舊 3 類）。
- 後果：首頁 5 欄 kanban 有 **3 欄永遠空**（模型動態/風險限制/倫理法規 顯示「這類目前沒有新內容」）；後端回傳的「邊界」資料 **整包被前端丟棄**（`theme-feed.tsx:29` 只迭代 `THEME_ORDER`）；`feed-summary.tsx:12` 摘要列同樣 3 欄恆 0、「邊界」計數蒸發。極端情況：只有「邊界」有資料時 `theme-feed.tsx:17` 的 `hasAny` 判 false → 明明有資料卻顯示全空狀態。
- 建議：後端 `ACTIONABLE_THEMES` 與 router `Theme` Literal 升級成 5 類（與 `ml/ml/theme.py` THEME_HYPOTHESES 對齊）；過渡期前端可把「邊界」映射到「風險限制」。加一條 contract test（前端 THEME_ORDER ⊆ 後端回傳鍵）。

**[A2] 來源篩選含後端不認得的 `ptt` → 選了直接整版報錯 — 高**
- 位置：`web/components/source-meta.tsx:61`（`SOURCE_ORDER` 含 `ptt`，且無 `reddit`）vs `api/api/routers/feed.py:20`（`Source` Literal：hackernews/devto/lobsters/threads/**reddit**，無 ptt）。
- 後果：使用者在來源下拉選「🟢 PTT」→ FastAPI 422 → `getFeed` 回 `ok:false` → 首頁主區顯示「無法載入情報，請確認 API 是否啟動」。一個合法的 UI 選項把整個 feed 弄壞，且錯誤訊息誤導（API 明明活著）。
- 建議：後端 Source Literal 補 `ptt`（DB 已有 PTT 語料）；或前端來源選項改由後端 `/api/sources` 提供，單一事實來源。

**[A3] API 預設埠 8000，本機實際 8010 → 開箱即全站錯誤 — 高**
- 位置：`web/lib/utils.ts:14-15`、`web/next.config.js:8`、`web/README.md:76`（皆 8000）vs 根 `README.md:139`「本機慣用 8010 埠」與記憶中本機跑法（API 8010）。實測：8000 無人聽、8010 有 python。web/ 無 `.env*` 檔。
- 後果：照文件起 API（8010）後開前端，整站每一區都是錯誤/空狀態，新手（含未來的自己）會以為壞了。這次實測兩個 Next 實例（3000/3001）都打 8000、全部 fetch 失敗。
- 建議：統一預設埠（建議 fallback 改 8010 並修 web/README）；加 `web/.env.local.example`；首頁可加開發模式提示（偵測到 API 連不上時顯示目前打的 BASE URL）。

**[A4] 「看全部」與主題列表頁 / 查詢頁不存在 — IA 斷頭 — 高**
- 位置：`web/components/theme-feed.tsx:12`（每主題固定 top 4，`getFeed(filters, 4)`）；全 `web/app/` 無 `/theme/[label]`、無 `/query`。對照 `docs/ux/positioning-c-ux.md` §3 IA 與驗收 **B4**（看全部須保留 filter）。
- 後果：使用者看到「新工具 4 則」之後**沒有任何路徑看第 5 則**；摘要列顯示計數（例如 23）但永遠只能看 4 張卡，計數變成挫折來源。深入只能靠把時間窗放大，違背「任何深入靠 filter 收斂」的設計原則。
- 建議：每欄標題列加「看全部 (N) →」連到 `/theme/[label]?model=…`（後端 `/api/feed?theme=` 已支援單主題加量，只是 Literal 要先修 A1）。

**[A5] 「今日事件」（產品差異化核心）大多數時候是空狀態，且錯誤偽裝成空 — 中**
- 位置：`web/components/today-events.tsx:100-107`：`!events.ok`（API 掛）與 `length===0`（真的沒事件）顯示幾乎相同的「尚無今日事件」。後端 `api/api/routers/events_today.py:113` 讀 `PULSE_EVENTS_FILE` JSONL，pipeline 沒跑就永遠 `[]`。
- 後果：首頁第一屏給差異化核心一整個 Section，但實際長期顯示「尚無今日事件 —— 等今天的貼文累積到可聚合的事件後會出現在這裡」；API 壞掉時使用者也無從分辨。空承諾傷信任。
- 建議：(1) 錯誤與空狀態分開文案；(2) 空狀態降級顯示「昨日事件」或最近一次成功產出的事件（檔案有日期就能做）；(3) 連續 N 天無產出時整區收合，不佔第一屏。

**[A6] SSR fetch 無 timeout — API 半死時整頁卡住 — 中**
- 位置：`web/lib/api.ts` 全部 fetch（無 `AbortSignal.timeout`）；`web/lib/pack.ts:20`（client 端生成材料包同樣無 timeout）。
- 後果：API 連線被接受但不回應時（例如 LLM 推論卡住、DB 鎖），Server Component 會一直 await，使用者面對白屏/舊頁。實測 dev 下 `/models/claude` 請求 >90 秒未完成（部分是 dev 編譯，但無 timeout 是事實）；既有 :3000 實例對同 URL 直接回 HTTP 500。
- 建議：所有 server fetch 加 `signal: AbortSignal.timeout(5000)`；材料包生成可放寬（60–120s）但要有 UI 取消鍵（見 C6）。

**[A7] `/models/[slug]` 404 判定靠錯誤字串比對 — 低**
- 位置：`web/app/models/[slug]/page.tsx:67`（`if (res.error === "HTTP 404") notFound()`）。
- 後果：脆弱；任何 api.ts 錯誤格式調整都會讓「查無模型」變成通用錯誤卡。
- 建議：`ApiResult` 失敗分支帶結構化 `status?: number`，以 `res.status === 404` 判定。

### B. 各頁體驗完整度（loading / 空 / 錯誤 / 回饋）

**[B1] 錯誤文案開發者導向，非產品語氣 — 高**
- 位置：`web/components/theme-feed.tsx:14`、`web/components/model-rail.tsx:10`、`web/app/decide/page.tsx:115`、`web/app/models/[slug]/page.tsx:74` —「請確認 API 是否啟動」。
- 後果：一般使用者不知道什麼是 API、更不會去「啟動」它；與 `error.tsx` 已經寫好的友善語氣（「可能是資料來源正在更新…你可以重試」）雙標。
- 建議：統一改成「資料暫時載入不了，稍後再試」＋重試動作；開發細節留 console。

**[B2] 首頁 API 全掛時的組合畫面破碎 — 中**
- 實測（API down）：主區「無法載入情報」紅字卡 + 左欄「無法載入模型」+ 今日事件「尚無今日事件」（偽空）+ 摘要列、熱詞欄**整塊靜默消失**（`feed-summary.tsx:9`、`trending-panel.tsx:6` 回 null）。
- 後果：同一個故障呈現四種不同行為（錯誤卡/偽空/消失/消失），版面忽缺忽現，使用者無法形成一致的心智模型。
- 建議：定義「區塊降級規範」：關鍵區顯示可重試錯誤卡、次要區顯示淡化 placeholder（而非消失），同一次故障全站文案一致。

**[B3] `/decide` 無 loading 狀態、送出後無回饋 — 中**
- 位置：`web/app/decide/page.tsx`（Server Component + 原生 GET form；無 `loading.tsx`、按鈕無 pending 態）。
- 後果：按「比較」後整頁等待 SSR（API 慢時數秒），按鈕無任何回饋，易重複點擊。
- 建議：加 `app/decide/loading.tsx` 骨架；或 form 加最小 client 增強（useFormStatus / 提交後 disable）。

**[B4] `/favorites` 首屏 SSR 全空（`return null`），無骨架 — 低**
- 位置：`web/components/favorites-list.tsx:66`（`if (!ready) return null`）。實測 SSR HTML 不含清單也不含空狀態。
- 後果：進頁瞬間只有標題，內容「跳出來」；慢機器上像壞掉。
- 建議：`!ready` 時渲染 2–3 張 `CardGridSkeleton` 而非 null。

**[B5] 首頁 ThemeFeed 骨架與實際版型不符 — 低**
- 位置：`web/app/page.tsx:76`（fallback `CardGridSkeleton count=6 cols=3`）vs 實際 `theme-feed.tsx:28`（xl 5 欄、每欄有標題列）。
- 後果：載入完成瞬間版面跳動（3 欄→5 欄）。
- 建議：做一個與 kanban 同構的骨架（5 欄、欄標題 + 2 卡）。

**[B6] 移除最愛無 undo、收藏頁直接消失 — 低**
- 位置：`web/components/favorite-button.tsx:28-31`（點 ♥ 立即移除）；favorites 頁中卡片移除即從格線消失。
- 建議：移除時給輕量 toast「已移除 · 復原」；或收藏頁中改為「待移除」標記，離頁才生效。

**[B7] 材料包錯誤訊息直接吐後端 detail / HTTP 碼 — 低**
- 位置：`web/lib/pack.ts:27-29` + `favorites-list.tsx:60`（`HTTP 500` 這類字樣會直接顯示給使用者）。
- 建議：對常見狀態碼映射成繁中文案（429 → 「請稍後再試」等），detail 留 console。

### C. 一致性（視覺 / 元件 / 文案）

**[C1] 主按鈕文字色不一致，且 `text-ink` 配寶藍底對比不足 — 中**
- 位置：`web/app/decide/page.tsx:105`、`web/app/models/[slug]/not-found.tsx:18` 用 `text-ink`（深岩藍 #1B2536 壓在 #4D74EA 上，對比約 2:1，WCAG 不及格）；`web/app/error.tsx:38`、`web/components/favorites-list.tsx:99` 用 `text-white`。
- 建議：統一主按鈕為 `bg-accent-primary text-white`；抽成 `ui/button.tsx`（目前按鈕樣式在 5+ 處手刻，重複造輪子）。

**[C2] trend-chart 硬編色違反「2 色克制」設計系統 + 暗色殘留 — 中**
- 位置：`web/components/charts/trend-chart.tsx:73-74`（紫 `rgb(139 92 246)`）、`:105`（cyan `rgb(6 182 212)`，雖然 tailwind 的 accent-cyan 已被收斂成寶藍，這裡繞過了 token）、`:97` 中性基準線 `rgb(255 255 255 / 0.12)` —— **白線畫在白卡上，淺色主題下不可見**（dark theme 殘留）。
- 建議：改用 CSS 變數/currentColor 接 tailwind token；基準線改 `ink/15`。

**[C3] 情緒的視覺語彙自相矛盾 — 中**
- 位置：篩選器 `web/components/feed-filter.tsx:19-20` 用「🟢 正面 / 🔴 負面」（紅綠語彙）；實際卡片圓點 `feed-card.tsx:8-12` + `tailwind.config.ts:32-36` 是 正=寶藍、負=深灰（刻意 2 色克制）。另「未分析」(`ink/20`) 與「中性」(#8A97AC) 兩種灰肉眼難辨。
- 後果：使用者從篩選器學到紅綠，回到卡片找不到紅綠；藍點直覺上不會被讀成「正面」。
- 建議：擇一：(a) 篩選器 emoji 改成與點同色的 ●（藍/灰）；(b) 或承認情緒就是需要紅綠第三色。未分析點改空心圓框與實心灰區隔。

**[C4] 七個死碼元件 + 兩套過時文案 — 中**
- 位置：`how-to-use.tsx`、`model-board.tsx`、`model-card.tsx`、`today-summary.tsx`、`events-feed.tsx`、`events-filter.tsx`、`releases-feed.tsx`（grep 證實無任何 import）。`how-to-use.tsx:8-24` 的三步驟還在講「事件動態/模型看板/決策報告」舊 IA。
- 建議：刪除或搬 `_legacy/`；HowToUse 若要復用需改寫成新 IA（見 D1）。

**[C5] Hero 詞彙與主題標籤不同步 — 低**
- 位置：`web/components/hero-intro.tsx:10`「新工具、模型動態、怎麼用、風險與倫理」vs 欄位標籤「使用方法 / 風險限制 / 倫理法規」。
- 建議：Hero 直接引用 `THEME_ORDER` 的字（單一事實來源），或至少用同樣詞。

**[C6] 材料包生成中只有「生成中…」，無進度/估時/取消 — 中**
- 位置：`web/components/favorites-list.tsx:101`。地端 LLM 蒸餾多主題可能要數十秒～分鐘。
- 建議：按鈕外加一行「正在用地端模型蒸餾 N 個主題，約需 X 秒…」；多主題可考慮後端逐主題串流或前端輪詢；提供取消（配 A6 的 AbortController）。

**[C7] 「儀表板」用語殘留舊定位 — 低**
- 位置：`web/components/site-nav.tsx:9`（導覽「儀表板」）、`web/app/models/[slug]/page.tsx:208` 與 `not-found.tsx`（「回儀表板」）。產品門面已是「每日實用情報」，非儀表板。
- 建議：導覽改「今日情報」或「首頁」，BackLink 改「← 回今日情報」。

**[C8] 收藏相關文案前後矛盾感 — 低**
- 位置：`web/components/favorites-list.tsx:69`「這裡會留著（每週清空不影響）」—— 「每週清空」指 feed 滾動窗，但首頁從未告訴使用者 feed 會每週清空；`web/app/favorites/page.tsx:15` 又說「跨週留存」。兩處講同件事用不同框架。
- 建議：統一說法：「收藏存在這台瀏覽器，不會隨每日情報過期」。

### D. 可發現性 / 新手理解

**[D1] 沒有任何 onboarding：核心動線（收藏→材料包）靠運氣發現 — 高**
- 位置：唯一的引導元件 `how-to-use.tsx` 是死碼（C4）。♥ 按鈕預設 `text-ink/25`（`favorite-button.tsx:35`）極淡、無文字標籤；首頁無一字提到「可以收藏」「收藏可以蒸成材料包」。新使用者要：注意到淡灰愛心 → 點它 → 自己想到去「我的最愛」→ 才看到材料包說明。
- 建議：(1) 重寫 HowToUse 為新 IA 三步（掃今日五類 → 篩模型 → ♥ 收藏蒸材料包）並掛回首頁；(2) 第一次點 ♥ 時 toast「已收藏 → 去我的最愛生成材料包」；(3) 導覽「我的最愛」旁顯示收藏數 badge。

**[D2] 電子報功能在前端零入口 — 中**
- 位置：`web/` 全目錄 grep「電子報 / newsletter」零命中。每日電子報（摘要+圖表+SMTP）是既有功能，但網站上完全不可發現。
- 建議：頁尾或 Hero 下加「訂閱每日電子報」入口（即使先連到說明頁/`mailto`）；長期做訂閱 API。

**[D3] 「Live」指示恆亮、無資料新鮮度資訊 — 低**
- 位置：`web/components/site-header.tsx:18-21` + `live-dot.tsx`。資料實際是 ISR 60s + 每日批次爬蟲；「Live」過度承諾。又 `lib/time.ts:3` 註明相對時間凍結在 revalidate 當下。
- 建議：改顯示「資料更新於 X 分鐘前」（從 API 帶 last_crawled_at），比恆亮綠點誠實有用。

**[D4] Threads 中文在地差異化標記不醒目 — 低**
- 位置：`web/components/source-meta.tsx:42-46`（🧵 Threads，`local:true` 只反映在 hover title）。對照 positioning §4.1 / 驗收 A5 要求 `🌏` 標記凸顯中文在地。
- 建議：local 來源徽章加 🌏 前綴或「中文」字樣，讓掃視時就能分辨在地內容。

**[D5] 手機上次要側欄排在主內容之前 — 中**
- 位置：`web/app/page.tsx:50-54`（`<aside>` ModelRail 在 DOM 序最前；窄螢幕 grid 堆疊時它排第一）。
- 後果：行動裝置第一屏被「依模型瀏覽」清單佔據，核心的篩選列與主題卡被推到下方。
- 建議：用 `order-*` 讓窄螢幕時主區先、側欄後；或行動版把模型清單收成水平 chip 列。

**[D6] 篩選變更不進歷史、無清除捷徑 — 低**
- 位置：`web/components/feed-filter.tsx:51`（`router.replace`）。連點三個 filter 後按「上一頁」會直接離站，與「可分享、可後退」的設計註解（`page.tsx:5`）矛盾；也沒有「清除全部篩選」。
- 建議：改 `router.push`（或至少模型 chip 用 push）；篩選非預設時顯示「× 清除」。

**[D7] 「今日」其實是近 24 小時滾動窗 — 低**
- 位置：`web/components/feed-filter.tsx:31`（label「今日」= days=1）+ `page.tsx:29` 註解自承「滾動視窗」。凌晨打開「今日」會看到大量「昨天」的卡，計數也對不上直覺。
- 建議：label 改「近 24 小時」，或後端支援 calendar-day 切窗。

**[D8] InfoHint 提示在觸控裝置幾乎不可用 — 低**
- 位置：`web/components/ui/info-hint.tsx:20`（純 hover/focus-within 顯示）。手機點按鈕不一定取得 focus（iOS Safari），等於行動版看不到指標定義。
- 建議：加最小 client 切換（點擊 toggle），或改 `<details>`。

**[D9] sitemap 收錄純個人頁 `/favorites` — 低**
- 位置：`web/app/sitemap.ts:8`。該頁內容全在 localStorage，對搜尋引擎是空頁。
- 建議：自 sitemap 移除，metadata 加 `robots: { index: false }`。

---

## 3. 做得好的（保持）

- `ApiResult` 判別聯集 + 「絕不 throw」的資料層（`lib/api.ts`），首頁單區故障不會整頁白屏；`error.tsx` / `global-error.tsx` / `not-found.tsx` / `loading.tsx` 四件套齊全，`global-error` 還刻意 inline style 自保。
- Suspense 串流 + 區塊級骨架（`ui/skeleton.tsx` 與卡片同格線）；篩選狀態走 URL params 可分享。
- `theme-meta` / `source-meta` 中介資料含未知值兜底（`themeMeta()` / `sourceMeta()` 絕不回 undefined），對後端字串變動有韌性。
- a11y 基礎好：全域 `focus-visible` ring、`prefers-reduced-motion`、`aria-pressed` / `aria-label` / `aria-current` 普遍存在；情緒「未分析」誠實顯示不假裝中性。
- 設計系統紀律（2 色克制、Tailwind token、字型自託管、繁中語氣大致統一、emoji 與後端對齊的註解文化）。

---

## 4. 前 10 大最值得修的問題（依「使用者受傷程度 × 修復成本」排序）

| # | 問題 | 對應編號 | 嚴重度 | 一句話修法 |
|---|------|---------|--------|-----------|
| 1 | 前後端主題契約脫鉤：首頁 5 欄有 3 欄永遠空、「邊界」資料被丟棄 | A1 | 高 | 後端 ACTIONABLE_THEMES / Theme Literal 升級 5 類 + contract test |
| 2 | 來源篩選選 PTT → 422 → 整版「無法載入情報」 | A2 | 高 | 後端 Source Literal 補 `ptt`（一行）+ 改錯誤文案 |
| 3 | API 預設埠 8000 vs 實際 8010 → 開箱全站錯誤狀態 | A3 | 高 | 統一預設埠 + `.env.local.example` + 修 web/README |
| 4 | 每主題只給 4 張卡、無「看全部」、`/theme` `/query` 缺頁 → IA 斷頭、計數變挫折 | A4 | 高 | 欄標題加「看全部 (N) →」+ 補 `/theme/[label]` 頁（後端 `?theme=` 已支援） |
| 5 | 零 onboarding：收藏→材料包（招牌新功能）幾乎不可發現 | D1 | 高 | 重寫 HowToUse 掛回首頁 + 首次收藏 toast + 導覽收藏數 badge |
| 6 | 錯誤文案「請確認 API 是否啟動」開發者導向，且全站降級行為四種不一致 | B1+B2 | 高 | 統一友善錯誤卡（可重試），次要區降級 placeholder 而非消失 |
| 7 | 「今日事件」常駐空狀態 + API 錯誤偽裝成空 → 差異化核心變空承諾 | A5 | 中 | 錯誤/空分開文案、降級顯示最近一次事件、連續無產出則收合 |
| 8 | SSR/材料包 fetch 無 timeout，API 半死整頁卡住（實測 >90s） | A6 | 中 | 全部 fetch 加 `AbortSignal.timeout`，材料包加取消 |
| 9 | 視覺一致性三連：主按鈕 `text-ink` 對比不足、trend-chart 硬編紫/白線不可見、情緒紅綠 emoji vs 藍灰點矛盾 | C1+C2+C3 | 中 | 抽 `ui/button`、圖表改 token 色、情緒語彙擇一統一 |
| 10 | 行動版第一屏被模型側欄佔據 + 材料包生成無進度回饋 | D5+C6 | 中 | 窄螢幕調 DOM/order 讓主區先；生成中顯示主題數與估時 |

> 次優先（修起來便宜可順手）：死碼七元件清理（C4）、Hero/主題詞彙同步（C5）、「儀表板」用語（C7）、「今日」→「近 24 小時」（D7）、favorites 骨架（B4）、🌏 在地標記（D4）。
