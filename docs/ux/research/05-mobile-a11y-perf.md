# UX 研究 05 — 行動端、無障礙與感知效能審計

> 範圍：`web/`（Next.js 14 App Router、Tailwind、零圖片、自託管字型）。
> 方法：靜態程式碼審計（逐元件讀碼 + WCAG 對比度計算），未跑瀏覽器實測。
> 背景：主要流量來自 Threads 貼文 → **手機直接點進來是預設情境**。
> 日期：2026-06-12

---

## 0. 現況快照（先說好的部分）

在進入問題清單前，先記錄已做對的事，避免後續修改誤刪：

- **Server Component 為主、client 邊界極小**：`'use client'` 只出現在 `site-nav`、`feed-filter`、`events-filter`、`favorite-button`、`favorites-list`、`error.tsx`、`global-error.tsx`。首屏 JS 極輕，這是行動端感知效能的最大優勢，務必維持。
- **Suspense 串流 + 骨架屏**：首頁每個資料區塊都有獨立 Suspense fallback（`app/page.tsx:51,59,69,76,84`），API 慢時版面不跳動。
- **零圖片內容** → `next/image` 議題不存在；OG 圖用 `opengraph-image.tsx` 動態生成，不佔首屏。
- **字型策略正確**：三個 woff2 共約 132KB、全部 `display: "swap"`（`app/layout.tsx:9-27`）；中文（內容主體）直接走系統字型（PingFang TC / Microsoft JhengHei，`tailwind.config.ts:39`），**不下載 CJK webfont** — 行動網路下這是對的取捨，中文無 FOIT/FOUT 問題。
- **`prefers-reduced-motion` 已全域處理**（`app/globals.css:26-33`）。
- **`focus-visible` ring 已全域處理**（`app/globals.css:14-23`）。
- **語意標籤大致到位**：`header/nav/main/footer/section/article/figure/time` 都有用；`html lang="zh-TW"`；nav 有 `aria-current`；篩選 chip 有 `aria-pressed`；收藏鈕有 `aria-pressed` + `aria-label`。
- **ISR 60 秒**（`lib/api.ts:30`）：回訪命中快取，TTFB 穩定。

以下問題是在這個底子上的「最後一哩」缺口。

---

## 1. 行動端審計

### 1.1 〔嚴重〕iOS 表單聚焦自動縮放：所有表單控制項字級 < 16px

- **位置**：
  - `web/components/feed-filter.tsx:58`（`<select>` 為 `text-[12px]`）
  - `web/components/events-filter.tsx:67`（同樣 `text-[12px]` select）
  - `web/app/decide/page.tsx:101`（議題 `<input>` 為 `text-sm` = 14px）
- **情境**：iOS Safari 在表單控制項 font-size < 16px 時，聚焦會**強制放大整頁**。手機使用者點「情緒／來源／時間」下拉（首頁核心互動）→ 頁面突然 zoom in，選完還停在放大狀態，要手動捏回來。
- **嚴重度**：高（核心互動、每次必踩）。
- **修法**：行動斷點下把表單控制項提到 16px：`className="text-base sm:text-[12px] ..."`；或統一改 `text-[16px] leading-tight` 並縮 padding 補償視覺。**不要**用 `maximum-scale=1` 壓掉縮放（違反 WCAG 1.4.4，Android 也會擋使用者放大）。

### 1.2 〔嚴重〕Header 在 ≤375px 裝置溢出 → 整頁橫向捲動

- **位置**：`web/components/site-header.tsx:11-22`、`web/components/logo.tsx:25`
- **情境**：header 是單列不換行 flex：Logo（含 26px 手寫體 wordmark ≈96px）+ px-6 內距（48px）+ 三個導覽連結（儀表板/我的最愛/決策報告 ≈177px）+ Live 指示（≈35px）+ gaps ≈20px ≈ **376px**。iPhone SE / 多數 Android（360px）會溢出；header 是 sticky，溢出會讓**整頁出現橫向捲動**且 sticky 定位錯位。
- **嚴重度**：高（小螢幕直接版面壞掉）。
- **修法**（擇一）：
  1. 最小改動：`<375px` 隱藏 Live 指示與 wordmark（`<Logo markOnly />` 已支援，`hidden xs:inline` 切換）；
  2. 正解：行動端導覽收進右上漢堡或改**底部 tab bar**（三個一級頁面正好適合 bottom tab，拇指可達性也最好）。目前**沒有漢堡選單也沒有底部 tab**，三連結硬塞頂列。

### 1.3 〔嚴重〕觸控目標普遍 < 44×44px（Apple HIG 44pt / WCAG 2.5.8 24px）

清單（依重要度）：

| 元件 | 位置 | 實際尺寸（估） | 說明 |
|---|---|---|---|
| 收藏愛心 | `favorite-button.tsx:33-39`（`p-1` + `h-4` icon） | **24×24px** | 手機上的**頭號收藏入口**，且浮在整卡外連結上 — 按不準就直接彈出 Threads 原文，操作成本極高 |
| 收藏勾選框 | `favorites-list.tsx:118-124`（`h-4 w-4`） | 16×16px | 同樣壓在整卡連結上，誤觸開外連 |
| 「AI 蒸餾」checkbox | `favorites-list.tsx:88-93`（`h-3.5 w-3.5`） | 14×14px | label 文字也只有 `text-xs` |
| 篩選 chips | `feed-filter.tsx:72-86`、`events-filter.tsx:46-60`（`px-2.5 py-1 text-[12px]`） | 高 ≈26px | 首頁核心篩選 |
| 篩選 selects | `feed-filter.tsx:55-66` | 高 ≈26px | 同上 |
| 導覽連結 | `site-nav.tsx:18,30`（`px-2.5 py-1 text-[13px]`、`gap-1`） | 高 ≈27px、間距 4px | 相鄰目標太近 |
| 行內引用 [1][2] | `today-events.tsx:30`（`text-[10px]` 上標）、出處列 `today-events.tsx:79` | ≈14px | 摘要出處是產品差異化賣點，手機上幾乎點不到 |
| InfoHint 問號 | `ui/info-hint.tsx:14-17`（`h-3.5` icon、無 padding） | 14×14px | |
| 回儀表板 | `models/[slug]/page.tsx:203-209`（`text-xs`） | 高 ≈16px | 詳情頁唯一返回入口 |
| 工具列按鈕 | `favorites-list.tsx:80-84,96-102`、`PackResult` `:161-178`（`py-1`~`py-1.5`） | 高 26–32px | 「生成材料包」是主 CTA |

- **修法**：通用模式是「視覺尺寸不變、命中區域擴大」：對小 icon 鈕用 `p-2.5`（或 `before:absolute before:-inset-2`）補到 ≥44px；chips/連結改 `py-2`；引用連結加 `inline-block px-1.5 py-1 -my-1`。收藏愛心建議直接做到 40–44px 命中區並與整卡連結保持 8px 安全距。

### 1.4 〔中〕行動端內容順序：模型側欄排在情報之前

- **位置**：`web/app/page.tsx:48-54`（`lg:grid-cols-[190px_1fr]`，aside 在 source order 第一位）
- **情境**：< lg 時 grid 變單欄、依 DOM 順序堆疊 → 手機首屏是 Hero →「依模型瀏覽」6 列清單 → 才到篩選器與今日事件。從 Threads 點進來的人要的是「今天的情報」，模型清單把它往下推了一整屏。
- **嚴重度**：中（不壞、但首屏價值被稀釋）。
- **修法**：grid 子項加 `order-*`：aside `order-2 lg:order-none`、主區 `order-1 lg:order-none`；或行動端把 ModelRail 摺成水平捲動 chip 列放在篩選器旁。

### 1.5 〔中〕五主題 kanban 在手機 = 超長單欄，無區內導航

- **位置**：`web/components/theme-feed.tsx:28`（`grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5`）
- **情境**：手機單欄時，五個主題區（每區最多 4 卡 + 標頭）垂直串成 ~20 張卡的長捲動；想看「倫理法規」要捲過前四區，也沒有錨點/跳轉。
- **嚴重度**：中。
- **修法**：行動端在 FeedSummary（已列五主題計數，`feed-summary.tsx:11-21`）把每個主題做成 anchor 連結（`href="#theme-新工具"` + ThemeFeed section 加 `id` + `scroll-mt-20`）；或行動端改主題 tab 切換。

### 1.6 〔低〕橫向溢出其餘風險點：大致安全

- 長 URL／長英文標題：FeedCard 標題/摘要都有 `line-clamp-*`（`feed-card.tsx:52,57,60`）、ReleaseCard 用 `truncate`（`release-card.tsx:34-35`）→ 安全。
- 材料包預覽 `<pre>`：`favorites-list.tsx:180` 有 `overflow-auto` → 內容不撐版，但行動端 `max-h-72` + 11px mono 閱讀吃力（低嚴重度，可附「全螢幕預覽」或直接引導下載）。
- TrendChart 是 `viewBox` + `preserveAspectRatio="none"` 的流式 SVG（`charts/trend-chart.tsx:66-69`）→ 不溢出，但窄螢幕會橫向壓縮波形（可接受）。
- 表格：全站無 `<table>` → 無風險。
- **未處理 safe-area**：全站找不到 `env(safe-area-inset-*)`/`dvh`。目前無固定底欄所以還好；若依 1.2 建議改 bottom tab，必須加 `pb-[env(safe-area-inset-bottom)]`。

### 1.7 〔低〕小螢幕字級可讀性

- 全站大量 `text-[10px]`（Badge，`ui/badge.tsx:7`，還加 `uppercase tracking-wider`）、`text-[11px]`（時間戳、出處、metric 標籤）。對「掃讀情報」的輔助資訊這是可接受的層級設計，但 10px 已低於行動可讀下限（建議 ≥11px），Badge 上又疊 mono+uppercase+加寬字距，中文 fallback 後字距會更怪。
- **修法**：Badge 升到 `text-[11px]`；中文內容的 Badge 拿掉 `uppercase tracking-wider`（對 CJK 無意義）。

---

## 2. 無障礙審計

### 2.1 〔嚴重〕對比度系統性不足（淺色主題 + 透明度階）

文字色全靠 `text-ink/NN`（#1B2536 疊不同透明度）落在 #FFFFFF 卡片/#F4F7FC 底上。實算對比：

| Token | 疊白後 | 對比度 | WCAG AA (4.5:1 normal / 3:1 large) |
|---|---|---|---|
| `text-ink/55` | ≈#82878F | **3.6:1** | ✗ 普通字級不及格 — 用在卡片摘要 `feed-card.tsx:60`、主題說明、大量 13px 內文 |
| `text-ink/45` | ≈#989DA5 | **2.7:1** | ✗ — metric 標籤、時間戳、頁面副標（`favorites/page.tsx:14`） |
| `text-ink/40`、`/35` | | **2.5 / 2.2:1** | ✗ — 時間 `feed-card.tsx:65`、熱詞說明 `trending-panel.tsx:16` |
| `text-ink/25`（愛心未收藏態） | | **1.7:1** | ✗ 連 UI 元件 3:1 都不過（`favorite-button.tsx:35`） |
| `accent-primary` #4D74EA on white | | **4.2:1** | ✗ 普通字級差一點（引用連結 10px、`text-accent-primary` 各處）；大字/UI 可 |
| 白字 on `bg-accent-primary`（主 CTA） | | **4.2:1** | ✗ 14px 按鈕字marginal 不及格（`favorites-list.tsx:99`、`error.tsx:38`） |
| `sentiment-neutral` #8A97AC | | **3.0:1** | ✗ 文字用途不及格 |

- **情境**：戶外手機 + 高環境光（Threads 使用情境）下，3.6:1 的 13px 摘要實際上是「看得到但讀不動」。
- **嚴重度**：高（全站性、影響所有內文層級）。
- **修法**：建立不透明灰階 token 取代透明度階的「文字用途」部分：次要文字至少 `ink/70`（≈6.7:1）、輔助文字至少 `ink/60`（≈4.5:1，剛好 AA）；時間戳等非必要資訊維持低對比但提供結構替代（`<time datetime>` 已有）。CTA 藍可微深（例 #3D63DB ≈5.0:1 對白字）。

### 2.2 〔嚴重〕來源徽章用暗色主題遺留色票，淺底上對比 1.9–2.8:1

- **位置**：`web/components/source-meta.tsx:31-57` — `text-orange-500`（2.8:1）、`text-violet-400`（2.1:1）、`text-emerald-400`（**1.9:1**）、`text-red-400`（2.5:1），且字級只有 10px。
- **情境**：來源（Threads/PTT＝在地差異化賣點）在手機上幾乎是裝飾色塊，讀不出字。
- **嚴重度**：高。
- **修法**：換 600/700 階（`text-orange-700`≈4.9、`text-violet-700`、`text-emerald-700`、`text-red-700`），淡底 `/10` 可留。

### 2.3 〔嚴重〕趨勢圖暗色主題遺留：白色基準線畫在白卡上＝隱形

- **位置**：`web/components/charts/trend-chart.tsx:97`（中性基準線 `stroke="rgb(255 255 255 / 0.12)"` — 白卡上**完全看不見**，圖例卻寫「中性線=0」`:81`）；`:73-74` 紫 `rgb(139 92 246)`、`:105` 青 `rgb(6 182 212)` 也非設計系統的 2 色（寶藍 #4D74EA）。
- **嚴重度**：高（功能性資訊缺失：使用者無從判斷口碑在正負哪一側）。
- **修法**：基準線改 `rgb(27 37 54 / 0.15)`；線色改 `#4D74EA`。另補充：SVG 已有 `role="img"` + `aria-label`（好），但口碑數值無文字替代 — 圖下方補一行「最新口碑 +12（偏正面）」文字即可同時服務 SR 與手機掃讀。

### 2.4 〔中〕情緒圓點：純色彩 + 只有 title（觸控與 SR 都拿不到）

- **位置**：`web/components/feed-card.tsx:14-20` — 8px 圓點，語意只放在 `title`。
- **情境**：`title` 在觸控裝置**不會顯示**、多數 SR 對非互動元素也不讀 title → 手機使用者完全得不到「正面/負面」資訊；色弱使用者連顏色都分不出（正=寶藍、中性/負=灰階，違反 WCAG 1.4.1 不得僅用顏色）。
- **修法**：加 `<span class="sr-only">情緒：正面</span>`；視覺上正/負已靠藍/灰區分但太隱晦，建議負面加形狀差異（如空心/實心）。同類問題：`model-card.tsx:18-24` 升溫小點、`model-rail.tsx:22-27` 升溫小點（有 `aria-hidden` + title，SR 與觸控都拿不到）、全站大量 `title=` 提示（`event-card.tsx:38`、`model-card.tsx:28,35` 等）在手機上全部失效 — 重要語意請改 InfoHint 或可見文字。

### 2.5 〔中〕InfoHint tooltip：無 aria 關聯、觸控無法關閉

- **位置**：`web/components/ui/info-hint.tsx:8-26`
- 問題：(1) 註解宣稱「tooltip 內容也放進 sr-only」但**實際沒有** — `role="tooltip"` 的內容未以 `aria-describedby` 關聯到 button，SR 讀到的只有「XX：說明」按鈕名，內容拿不到；(2) 觸控上靠 `focus-within` 顯示，但沒有 Esc/點外關閉（WCAG 1.4.13），且 tooltip `w-56` 置中定位在螢幕邊緣的 Metric 卡上會被裁切。
- **修法**：button 加 `aria-describedby={id}`、tooltip 加 `id`；加 `onKeyDown` Esc blur；行動端考慮改成點擊展開的行內說明。

### 2.6 〔中〕收藏流程的動態結果無 ARIA live region

- **位置**：`web/components/favorites-list.tsx:105-111`（錯誤訊息）、`:111` `PackResult`（生成成功區塊）、`:101`（「生成中…」只改按鈕文字）
- **情境**：SR 使用者按下「生成材料包」後，成功/失敗/進行中**完全沒有播報**；結果區塊插在工具列上方，視覺使用者也可能沒注意到（生成後焦點還停在按鈕）。
- **修法**：錯誤與結果容器加 `role="status"` / `aria-live="polite"`；生成完成把焦點移到結果區（`ref.focus()` + `tabIndex={-1}`）。

### 2.7 〔中〕鍵盤可操作性與焦點順序

- 整體良好（原生 button/a/select/checkbox + 全域 focus-visible ring）。缺口：
  - **無 skip link**：每頁 Tab 都要先過 logo + 3 導覽 + 篩選 chips（首頁 6 個模型 chip）才到內容。`app/layout.tsx:58-65` body 開頭加「跳到主要內容」+ `main id="main"`。
  - FeedCard 整卡隱形連結（`feed-card.tsx:30-38`）：鍵盤聚焦時 ring 畫在整卡（可接受），但 aria-label 用 `post.title`（英文原題）而視覺顯示 `title_zh` — SR 中文使用者聽到英文。改用 `post.title_zh ?? post.title`。
  - 收藏勾選框 aria-label 全部相同「選取此收藏」（`favorites-list.tsx:122`）→ SR 清單導航無法區分。改 `aria-label={`選取：${p.title_zh ?? p.title}`}`。
- 燈箱/對話框/focus trap：**全站沒有 modal**，無此議題（材料包結果是行內區塊，正確的簡單選擇）。

### 2.8 〔低〕其他

- `app/decide/page.tsx:103-108`：提交鈕 `bg-accent-primary` + **`text-ink`**（深字on藍底 = 3.7:1 不及格），且與全站其他主 CTA 的 `text-white` 不一致 — 應是筆誤。
- `model-card.tsx:47`：「查看詳情」用 `text-ink/0`（隱形）hover 才顯色 — 觸控裝置永遠看不到；連結本身可點所以無功能問題，但建議行動端常駐顯示。
- 標題層級：首頁 h1（hero）→ h2（今日事件/依模型瀏覽/本週熱詞）→ h3（主題欄、卡片）大致合理；ThemeFeed 的五個 `<section>`（`theme-feed.tsx:33`）建議加 `aria-labelledby` 指向主題 h3。
- emoji：篩選 select 選項含 emoji（`feed-filter.tsx:27`）會被 SR 逐字唸；錯誤訊息 `⚠️ {error}`（`favorites-list.tsx:107`）emoji 未隱藏。低優先。
- 深色模式：`colorScheme: "light"` 硬鎖（`layout.tsx:55`、`globals.css:7`）。手機夜間使用（Threads 場景常見）會很刺眼；tailwind 已設 `darkMode: "class"` 但無任何 dark token。列為 backlog，不算違規。

---

## 3. 感知效能審計

### 3.1 首屏組成（好底子，兩個小尾巴）

- Server/client 邊界乾淨（見 §0）。首屏 client JS 僅 nav + 篩選器 + 每卡一個 FavoriteButton。FavoriteButton 每張卡掛一個 listener（`favorite-button.tsx:15-20`），20+ 卡 = 20+ 個 `window` listener — 量級無感，暫不需改。
- `animate-fade-up` 入場動畫 0.55s（`page.tsx:44,48`、`globals.css:55-61`）：對「從 Threads 點進來快速掃一眼」的使用者是純延遲。建議縮到 0.3s 以下或只保留 Hero。
- 死碼：`how-to-use.tsx`、`model-board.tsx`、`events-feed.tsx`、`releases-feed.tsx` 已無任何引用（Next 按路由 tree-shake 不會進 bundle，但維護上建議刪）。

### 3.2 〔中〕清單策略：無分頁也無「看更多」

- **位置**：`app/page.tsx:76`（`getFeed(filters, 4)` 每主題固定 4 篇）、`lib/api.ts:99`（今日事件固定 8）
- 好處：手機上不會無限長、無需虛擬化。缺口：使用者想看第 5 篇起的內容**沒有任何入口**（只能調時間篩選），feed 是死路。建議每主題欄底加「更多 ○○ →」（query param `?theme=新工具&limit=20` 的列表頁），維持 SSR 分頁即可，不需要無限捲動。

### 3.3 〔中〕PWA：有 manifest、無 service worker、icon 不齊 → 「可安裝」承諾未兌現

- **位置**：`web/app/manifest.ts:16-18` — icons 只有 `icon.svg`；全站無任何 service worker（無 `public/` 目錄、無 sw 註冊碼）。
- **情境**：(1) Android Chrome 安裝提示通常要求 **192px 與 512px PNG**（含 `purpose: "maskable"`），只給 SVG 可能不出現安裝列；(2) 已安裝的使用者在捷運斷網打開 → **瀏覽器錯誤頁**（standalone 模式下連網址列都沒有，體驗比瀏覽器更糟）。
- **修法**：補 `icon-192.png`/`icon-512.png`（+maskable）；加最小 SW（next-pwa 或手寫 30 行：precache offline.html，fetch fail 時回 fallback「離線中 — Pulse 需要連線抓今日情報」）。在 TLS 受限環境可手寫 SW 避免裝套件。

### 3.4 〔低〕字型載入細節

- `localFont` 預設會 preload 三個檔（132KB）；`dancing-script`（44KB）只用在 wordmark 一個單字 — 可 `preload: false` 或子集化到 "Pulse" 五個字母（<2KB）。
- `display: "swap"` + 中文走系統字型 → 無 FOIT；英文數字會有短暫 fallback 字形交換（FOUT），mono 數字（metric 卡）可能輕微跳動，可用 `adjustFontFallback`（next/font 預設開）已大致處理。維持現狀即可。

### 3.5 〔低〕sticky header `backdrop-blur-md`（`site-header.tsx:10`）

低階 Android 上捲動時 blur 合成有感。若實測掉幀，降級為純半透明底色即可。

---

## 4. 手機體驗前 10 大問題（依「影響 × 頻率」排序)

| # | 問題 | 位置 | 嚴重度 | 一句話修法 |
|---|---|---|---|---|
| 1 | iOS 點篩選 select/input 觸發整頁自動縮放（<16px） | `feed-filter.tsx:58`、`events-filter.tsx:67`、`decide/page.tsx:101` | 高 | 行動端表單控制項一律 ≥16px |
| 2 | Header 在 ≤375px 溢出 → 整頁橫向捲動、sticky 錯位；且無漢堡/底部 tab | `site-header.tsx:11-22` | 高 | 短期縮 Logo/藏 Live；正解改底部 tab（記得 safe-area） |
| 3 | 收藏愛心 24px 且浮在整卡外連結上 — 按不準直接彈去 Threads | `favorite-button.tsx:33-39`、`feed-card.tsx:30-39` | 高 | 命中區擴到 ≥44px + 與卡片連結保持安全距 |
| 4 | 內文層級對比系統性不及格（ink/55=3.6:1、ink/45=2.7:1…），戶外手機讀不動 | 全站，定義在 `tailwind.config.ts:22-24` 的用法 | 高 | 文字用途改 ink/70・/60 不透明階；CTA 藍加深 |
| 5 | 來源徽章暗色遺留色票（emerald-400=1.9:1 等）+ 10px 字 | `source-meta.tsx:31-57`、`ui/badge.tsx:7` | 高 | 換 600/700 階、Badge 升 11px |
| 6 | 趨勢圖白基準線畫在白卡上＝隱形；紫/青線非設計系統色 | `charts/trend-chart.tsx:73,97,105` | 高 | 基準線改 ink/15、線改 #4D74EA、補文字版口碑值 |
| 7 | PWA 安裝不齊（無 192/512 PNG、無 maskable）+ 無 SW → 離線開啟見瀏覽器錯誤頁 | `manifest.ts:16-18`、無 `public/` | 中 | 補 PNG icons + 最小離線 fallback SW |
| 8 | 篩選 chips/導覽/引用 [1] 等觸控目標 14–27px、間距 4px | §1.3 清單 | 中 | `py-2`、引用加 padding、相鄰目標拉開 |
| 9 | 行動單欄時模型側欄排在情報前 + 五主題長捲動無錨點 | `page.tsx:48-54`、`theme-feed.tsx:28` | 中 | `order-*` 調序 + FeedSummary 變主題錨點列 |
| 10 | 情緒/升溫等關鍵語意只放 `title` + 純色點 — 觸控與 SR 雙雙拿不到 | `feed-card.tsx:14-20`、`model-card.tsx:18`、`model-rail.tsx:22` | 中 | sr-only 文字 + 非顏色的形狀差異 |

**次一級 backlog**（不進前十但建議排入）：收藏流程 aria-live 與焦點管理（§2.6）、InfoHint aria-describedby/Esc（§2.5）、skip link（§2.7）、decide 提交鈕 `text-ink` 筆誤（§2.8）、feed 死路加「更多」入口（§3.2）、入場動畫縮短（§3.1）、深色模式（§2.8）。
