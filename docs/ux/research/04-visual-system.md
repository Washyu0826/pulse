# UIUX 研究 04：視覺設計系統與中文排版

> 研究範圍：`web/tailwind.config.ts`、`web/app/globals.css`、`web/app/layout.tsx` 與 31 個元件。
> 本文件為**提案**，未修改任何現有程式碼。對比度數值為近似計算（WCAG 2.x 相對亮度公式），落地前建議用工具複核。

---

## 1. 現況盤點

### 1.1 色彩 token（`tailwind.config.ts`）

| Token | 值 | 用途 |
|---|---|---|
| `bg` | `#F4F7FC` | 冷調淺藍白紙底 |
| `bg-card` | `#FFFFFF` | 卡片底 |
| `bg-cardLight` | `#EAF1FB` | hover 淺藍 |
| `border` | `#D9E2F1` | 邊框 |
| `ink` | `#1B2536` | 唯一文字色，深淺全靠 `text-ink/XX` 透明度 |
| `accent-primary` = `accent-cyan` = `accent-pink` | `#4D74EA` | 唯一彩色 accent（cyan/pink 為舊名別名，導向同色） |
| `sentiment-positive / neutral / negative` | `#4D74EA` / `#8A97AC` / `#5A6677` | 情緒三態（刻意不用紅綠） |

設計哲學明確且有註解佐證：「2 色克制（冷墨 ink + 單一藍 accent）」、情緒不引入紅綠。這個克制本身是優點，下面的問題多半是**漏網之魚**而非系統設計錯誤。

### 1.2 字級階層（實際使用盤點）

語意字級（Tailwind 預設）與任意值（arbitrary）並存，**同一視覺層級有多種寫法**：

| 實際尺寸 | 寫法 | 出現位置（例） |
|---|---|---|
| 10px | `text-[10px]` | badge.tsx、today-events.tsx |
| 11px | `text-[11px]` | feed-card 時間/原文對照、trend-chart 軸標、model-card……（最氾濫，13 處） |
| 12px | `text-xs` **和** `text-[12px]` 混用 | event-card 用 `text-xs`，feed-filter/events-filter 用 `text-[12px]`（同為 12px，兩種寫法） |
| 13px | `text-[13px]` | feed-card snippet、event-card 描述、model-rail……（12 處） |
| 14px | `text-sm` | 卡片標題、section 描述 |
| 15px | `text-[15px]` | hero 副標 |
| 17px | `text-[17px]` | Section h2 |
| 20px+ | `text-2xl`、`text-[26px]`（logo）、`text-[34px]`（hero h1） |

→ 實際只有約 8 個層級的需求，但寫法有 11 種。`text-xs` vs `text-[12px]`、`text-sm` vs `text-[13px]` 的並存代表沒有 token 約束，之後改階層要全域 grep。

行高：標題用 `leading-snug`（1.375），內文用 `leading-relaxed`（1.625）。**對中文而言兩者都偏緊**（見第 2 節）。`tracking-tight` 只用在英文向的大標與 `uppercase` badge（`tracking-wider`），中文內文無字距調整。

### 1.3 間距 / 圓角 / 陰影

- 間距：全走 Tailwind 預設 4px 階（`gap-1.5`、`p-5`、`mt-2.5`、`py-12`），無自訂 token，但使用上算一致。卡片內距固定 `p-5`（`.card`），節奏 OK。
- 圓角：`.card` 用 `rounded-xl`（12px）、badge `rounded-md`、skeleton/摘要列 `rounded-lg`，大致是「外大內小」的正確直覺，未 token 化。
- 陰影：`.card` 用 `shadow-sm shadow-ink/[0.03]`，hover 升 `shadow-md shadow-ink/[0.06]` + `-translate-y-0.5`，是系統內最一致的部分（集中在 `globals.css` `@layer components`）。

### 1.4 深色模式狀態：**未實作**

- `tailwind.config.ts` 設了 `darkMode: "class"`，但全 repo **0 個 `dark:` variant**。
- `globals.css` `:root { color-scheme: light }`、`layout.tsx` `viewport.colorScheme: "light"`、`themeColor: "#4D74EA"` 皆鎖定淺色。
- 結論：目前是「淺色單主題 + 留了開關但沒接線」。色彩 token 直接寫死 hex 在 Tailwind config，**沒有走 CSS 變數**，未來要上深色模式得整包改寫法（見第 4 節提案：token 改 CSS 變數，深色模式只要換變數值）。

### 1.5 不一致清單（依嚴重度排序）

1. **`trend-chart.tsx` 殘留舊深色主題的硬編碼色（含一個實際 bug）**
   - L97：口碑指數的中性基準線 `stroke="rgb(255 255 255 / 0.12)"` —— **白線畫在白卡片上，目前是隱形的**（舊深色主題殘留）。
   - L73–74：討論量面積/折線用 `rgb(139 92 246)`（violet-500）、L105 口碑線用 `rgb(6 182 212)`（cyan-500）—— 直接打破「2 色克制」，且不走 token。
2. **`source-meta.tsx` 的來源徽章色未過對比檢查，且混用 `-400`/`-500`（`-400` 是深色主題用的文字色）**
   - `text-orange-500`（#F97316）在白底 ≈ 2.8:1、`text-emerald-400`（#34D399）≈ 1.8:1、`text-violet-400` ≈ 3.0:1、`text-red-400` ≈ 2.6:1 —— badge 字級才 10px，WCAG AA 小字需 4.5:1，**全數不及格**（細節見 3.2）。
3. **低透明度 ink 文字在小字級上對比不足**
   - `text-ink/40`（時間戳、11px）疊在白卡上有效色約 `#9DA3AD`，對比 ≈ 2.4:1；`ink/55` ≈ 3.5:1；`ink/60` ≈ 3.9:1。13px 以下的次要文字建議底線拉到 `ink/70`（≈ 5.3:1）；`/40` 只留給純裝飾。
   - 全 repo 的 ink 透明度檔位多達 `/20 /35 /40 /45 /50 /55 /60 /70 /75 /85`——10 檔太碎，建議收斂成 4 檔語意 token（見第 4 節）。
4. **硬編碼 hex 重複定義品牌色**：`opengraph-image.tsx`、`global-error.tsx`、`layout.tsx`（themeColor）各自寫死 `#4D74EA / #F4F7FC / #1B2536`。OG image 與 global-error 不能用 Tailwind class 情有可原，但應抽到 `lib/site.ts` 之類的常數共用，否則改品牌色會漏。
5. **字級任意值氾濫**（1.2 節）：`text-[11px]`×13、`text-[13px]`×12 等，無 token。
6. **emoji 當識別符**：來源徽章同時放 emoji + 文字（`🟠 HN`），emoji 跨平台渲染不一致（Windows/macOS/Android 形色差很大），且與徽章色重複編碼。

---

## 2. 中文排版深研

### 2.1 行高與字距：中文要比英文鬆

中文方塊字無上下伸部（ascender/descender），筆畫密度高，視覺重心滿格；西文慣用的 1.4–1.5 行高在中文段落會顯得擁擠。業界慣例（Apple HIG 中文、Noto CJK 預設、W3C《中文排版需求》clreq）：

- **內文行高 1.7–1.9**（字號越小越需要鬆）。現況 `leading-relaxed`（1.625）給 13px 中文 snippet 偏緊，建議 1.75。
- **標題行高 1.3–1.5**。現況 hero `leading-[1.15]` 對純英文 OK，但「每天的 AI 實用情報」這種中文大標，1.15 會讓上下行幾乎貼字，建議 ≥ 1.25；卡片標題 `leading-snug`（1.375）勉強可，兩行中文 `line-clamp-2` 建議升到 1.5。
- **字距（letter-spacing）**：中文內文加 `0.01em–0.02em` 可提升小字級可讀性；標題不加或微縮。**`tracking-tight`（-0.025em）不要套到中文標題**——負字距會讓方塊字黏在一起。現況 hero h1 / Section h2 都套了 `tracking-tight`，因為標題是中英混排，英文部分受益、中文部分受害；建議中文為主的標題改 `tracking-normal`。
- **不要對 `uppercase` 以外的中文用 `tracking-wider`**：現況 Badge 用 `font-mono uppercase tracking-wider`，badge 內容若是英文模型名沒問題，但 `source-meta` 的「其他」、收藏頁等中文 badge 文字會被拉開字距 + mono 字型 fallback，視覺破碎。建議 badge 對中文內容關閉 tracking（或 badge 分 latin/cjk 兩種樣式）。

### 2.2 中英混排與標點

- **漢字與西文/數字之間留間隙**（俗稱「盤古之白」）：現況文案已手動加空格（如「每天的 AI 實用情報」），這是對的，**繼續以手動空格為主**；CSS `text-autospace`（CSS Text 4）已在 Safari 18.4+ / Chromium 新版陸續支援，可加上當漸進增強，對沒手動加空格的動態資料（爬來的貼文標題）特別有用：
  ```css
  :lang(zh-Hant) { text-autospace: normal; } /* 不支援的瀏覽器自動忽略 */
  ```
- **標點擠壓**：連續全形標點（如「」。）的空隙可用 `text-spacing-trim: space-first`（Chromium 123+）收斂，同樣是漸進增強，不依賴它。
- **斷行**：中文逐字可斷，預設即可；混排內容（URL、英文長詞）加 `overflow-wrap: break-word` 防爆版。**不要用 `word-break: break-all`**（會把英文單詞攔腰斬斷）。標題可加 `text-wrap: balance`（h1/h2）避免孤字行。
- **斜體**：`feed-card.tsx` L57 用 `italic` 標示英文原文對照——對英文 OK；但若 `title` 本身含中文，中文沒有斜體字形，瀏覽器會做假斜（shear），觀感差。建議：原文對照列改用「色彩降階 + 字級降階」就夠（拿掉 `italic`），或只對確定是 latin 的內容用斜體。

### 2.3 `font-family` fallback stack 怎麼排

現況（`tailwind.config.ts` L39）：

```
var(--font-sans) → system-ui → -apple-system → "PingFang TC" → "Microsoft JhengHei" → "Noto Sans TC" → sans-serif
```

兩個問題：

1. **`system-ui` 排在 CJK 字型前面基本無害但多餘**（Inter 已涵蓋 latin；macOS 的 system-ui 沒有的 CJK 會繼續往後找），真正的問題是——
2. **`Microsoft JhengHei` 排在 `Noto Sans TC` 前面**：Windows 使用者若自行裝了 Noto Sans TC（設計/工程族群常見），仍會吃到字重支援差、hinting 過時的微軟正黑體。Noto 應該排在 JhengHei 前面：裝了就用好的，沒裝才退到系統字。

建議 stack（zh-TW 優先；macOS/iOS → PingFang，有裝 Noto 的任何平台 → Noto，Windows 兜底 → JhengHei）：

```ts
fontFamily: {
  sans: [
    "var(--font-sans)",        // Inter（自託管，latin）
    "PingFang TC",             // macOS / iOS
    "Noto Sans TC",            // 有自行安裝者（含 Android 的 Noto Sans CJK）
    "Microsoft JhengHei",      // Windows 兜底
    "system-ui",
    "sans-serif",
  ],
  mono: [
    "var(--font-mono)",        // JetBrains Mono（自託管，latin）
    "Consolas", "ui-monospace",
    // mono 裡的中文會 fallback：明確指定與 sans 同套 CJK，避免瀏覽器亂配
    "PingFang TC", "Noto Sans TC", "Microsoft JhengHei",
    "monospace",
  ],
}
```

註：`-apple-system` 是 `system-ui` 標準化前的舊寫法，留 `system-ui` 即可。

### 2.4 中文要不要上 webfont？——**建議：不上全量，最多上「UI 字串微子集」**

成本面（考量本環境：npm/外網受限、字型已走 repo 自託管模式）：

| 方案 | 體積 | 可行性 |
|---|---|---|
| Noto Sans TC variable 全量 woff2 | 單檔約 4–9 MB | 首屏不可接受；`next/font/local` 會整檔載入 |
| Google Fonts 式 unicode-range 切片自託管 | 100+ 片、每片 5–30 KB，瀏覽器按需載 | 需一次性抓全部切片進 repo（外網受限下要走一次 truststore 流程）、`next/font/local` 不支援多 unicode-range 切片，得手寫 `@font-face` × 100，維護成本高 |
| 教育部常用字 4808 字子集（單字重） | 約 1–1.5 MB | 內容是爬來的動態貼文，**一定會出現子集外的字** → 缺字 fallback 到系統字，同一行裡兩種字形混搭，比全用系統字更難看 |
| **不上中文 webfont（現況）** | 0 | PingFang / JhengHei / Noto 三大平台系統字都是合格黑體 |
| UI 字串微子集（可選加分項） | < 50 KB | 只 subset **固定不變的 UI 字串**（導覽、五主題標籤、按鈕、hero 標語，約 150–300 字），用 fonttools `pyftsubset` 一次產出；動態內容照走系統字 |

**結論**：情報類產品內容為王、字符集不可預測，全量/大子集 webfont 的成本效益是負的。系統字 stack 排對（2.3）就已達標。若之後想要品牌感，做「UI 微子集」即可——固定字串永不缺字、體積與一張 icon 差不多。實作要點：`pyftsubset NotoSansTC.ttf --text-file=ui-strings.txt --flavor=woff2`，以 `next/font/local` 第四個字族 `--font-ui` 掛上，僅套在 nav/hero/section 標題等元件。

### 2.5 數字：等寬 vs 比例

- **敘述句中的數字**（「共 1,234 篇」讀過即走）：比例（proportional）即可，視覺融入文句。
- **會對齊/跳動的數字**（摘要列計數、趨勢圖軸標、相對時間、表格）：需要**等寬數字**，否則數字更新時寬度抖動。
- 現況用 `font-mono`（JetBrains Mono）當「資料聲音」——這是一個成立的設計決定（mono = 機器產出的資料），可以保留；但有更輕的替代：**Inter variable 自帶 `tnum`（tabular figures）**，`font-variant-numeric: tabular-nums` 就能讓 Inter 數字等寬，不必切字型、不會有 mono 中文 fallback 問題。建議：
  - 純數字/日期/計數 → 留 `font-mono`（風格）或改 `tabular-nums`（克制）擇一，**全站統一**；
  - 「13 篇 · 平日約 5 篇/天」這種中文夾數字的行 → 不要用 `font-mono`（中文會 fallback 出戲），改 `font-sans tabular-nums`。現況 `event-card.tsx` L56、`trend-chart.tsx` L63 都是中文夾數字卻套 mono，是字形混搭重災區。

---

## 3. 資訊密度視覺策略

### 3.1 卡片 vs 列表

現況：全站皆卡片（`.card` 3 欄 grid），含 11px/13px 多層文字。卡片適合「每則都值得駐足」的內容（今日事件、模型卡），但**主題 feed 一天幾十則時，卡片的邊框/陰影/內距是重複的視覺稅**，掃讀效率低於列表。建議分層：

- **今日事件、收藏材料包**：保留卡片（少量、高價值、有多層 metadata）。
- **主題 feed**：提供「密集列表」形態——單行 = 情緒點 + 標題 + 來源徽章 + 時間，行高 ~40px，hover 才浮出 snippet。一屏可從 ~9 則升到 ~20 則。可做成使用者切換（卡片/列表 toggle，存 localStorage），預設依數量自動：≤6 則卡片、>6 則列表。
- 卡片內部已有好的密度習慣（`line-clamp-2`、層級遞減），保留。

### 3.2 來源標識（HN / PTT / Threads…）

現況：emoji + 文字 + 各來源各色淡底徽章（`source-meta.tsx`）。方向正確（來源用約定俗成色：HN 橘、PTT 綠），但執行有三個問題：

1. **對比不及格**（1.5 節 #2）：`-400/-500` 文字色是深色主題的選擇，在白底 10px 全數低於 4.5:1。修法：同色相改用 `-700` 階當文字、`-500/10` 當底、`-500/30` 當框——色相識別保留、文字達標：

   | 來源 | 現況文字色 | 對比（近似） | 建議文字色 | 對比（近似） |
   |---|---|---|---|---|
   | HN | `orange-500` | 2.8:1 ✗ | `orange-700` #C2410C | 5.0:1 ✓ |
   | Dev.to | `violet-400` | 3.0:1 ✗ | `violet-700` #6D28D9 | 7.7:1 ✓ |
   | Threads | accent #4D74EA | 4.2:1 △ | `ink/85` 或加深 accent | ✓ |
   | PTT | `emerald-400` | 1.8:1 ✗ | `emerald-700` #047857 | 5.4:1 ✓ |
   | Lobsters | `red-400` | 2.6:1 ✗ | `red-700` #B91C1C | 6.0:1 ✓ |

2. **emoji 不可控**：建議拿掉徽章內 emoji（已有色彩 + 文字雙重編碼），或換成 2px 圓點（`bg-current`）——跨平台一致、不搶戲。
3. **「中文在地來源」（local）目前只藏在 title tooltip**：這是產品差異化主軸，值得視覺升級——local 來源徽章加一個小「在地」前綴點或實心樣式（filled vs outline），讓 Threads/PTT 一眼可辨。

### 3.3 主題 5 類的色彩編碼

現況：五主題**共用同一 accent 藍、靠 lucide icon 形狀區分**（`theme-meta.tsx` 有明確設計註解）。從可及性角度這其實是**優等生做法**——形狀編碼對任何色覺類型都有效，零色盲風險。評估：

- **維持「同色 + 形狀」為預設**。五個 icon（Sparkles/BarChart3/Wrench/AlertTriangle/Scale）形狀差異夠大。
- 若未來要上主題色（例如主題分區的視覺錨點、圖表分系列），**不要各配五個飽和色**，建議「藍色 ramp + 一個警示橙」：風險限制/倫理法規共用暖橙系、其餘三類用藍的深淺——保住 2 色哲學，又給圖表留路。若一定要 5 色，採 Okabe-Ito 色盲安全色盤的子集（見第 4 節 token，標記為 optional）。
- **情緒三態**現用 藍/灰/深灰 圓點，色盲安全 ✓，但「中性 vs 負面」兩個灰肉眼難分、且只有 2px 圓點 + tooltip。建議負面點改空心或加極小下降箭頭形狀差異；或列表形態時直接顯示「正/中/負」一字。

---

## 4. 設計 token 提案（可直接落地的片段）

核心改法：**色彩值下沉到 CSS 變數**（深色模式只要換 `:root.dark` 的變數值，元件零改動）、**字級收斂成含中文行高的 8 階**、**ink 透明度收斂成 4 檔語意層**。

### 4.1 `globals.css` 新增（變數 + 中文排版基建）

```css
@layer base {
  :root {
    color-scheme: light;
    /* ── 色彩（深色模式未來只改這裡）── */
    --bg: 244 247 252;            /* #F4F7FC */
    --bg-card: 255 255 255;
    --bg-card-hover: 234 241 251; /* #EAF1FB */
    --border: 217 226 241;        /* #D9E2F1 */
    --ink: 27 37 54;              /* #1B2536 */
    --accent: 77 116 234;         /* #4D74EA */
    --accent-strong: 56 92 204;   /* 深一階：白底小字可達 4.5:1 的 accent 文字用 */
    /* 情緒（維持無紅綠哲學） */
    --positive: 77 116 234;
    --neutral: 138 151 172;
    --negative: 90 102 119;
    /* 來源識別（文字用 -700 階，達 AA） */
    --src-hn: 194 65 12;          /* orange-700 */
    --src-devto: 109 40 217;      /* violet-700 */
    --src-threads: 56 92 204;     /* = accent-strong */
    --src-ptt: 4 120 87;          /* emerald-700 */
    --src-lobsters: 185 28 28;    /* red-700 */
  }

  /* 之後上深色模式：html.dark { --bg: ...; --ink: ...; } 即可，元件不動 */

  body {
    @apply bg-bg text-ink;
    overflow-wrap: break-word;          /* 混排長英文/URL 防爆版 */
  }

  /* 中文排版漸進增強（不支援的瀏覽器自動忽略） */
  :lang(zh-Hant) {
    text-autospace: normal;             /* 漢字與西文/數字自動留隙（動態爬文內容受益） */
    text-spacing-trim: space-first;     /* 連續全形標點擠壓 */
  }

  h1, h2 { text-wrap: balance; }        /* 標題避免孤字行 */
  p { text-wrap: pretty; }
}

@layer utilities {
  /* 中文夾數字的行：等寬數字但不切 mono 字型（取代 event-card/trend-chart 的 mono 混搭） */
  .nums { font-variant-numeric: tabular-nums; }
}
```

### 4.2 `tailwind.config.ts` theme 片段

```ts
const config: Config = {
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // 全部改讀 CSS 變數（<alpha-value> 讓 text-ink/60 等透明度寫法照常運作）
        bg: {
          DEFAULT: "rgb(var(--bg) / <alpha-value>)",
          card: "rgb(var(--bg-card) / <alpha-value>)",
          cardLight: "rgb(var(--bg-card-hover) / <alpha-value>)",
        },
        border: { DEFAULT: "rgb(var(--border) / <alpha-value>)" },
        ink: { DEFAULT: "rgb(var(--ink) / <alpha-value>)" },
        accent: {
          primary: "rgb(var(--accent) / <alpha-value>)",
          strong: "rgb(var(--accent-strong) / <alpha-value>)", // 小字 accent 文字用
          // cyan/pink 舊別名：過渡期保留指向 primary，元件改完即刪
          cyan: "rgb(var(--accent) / <alpha-value>)",
          pink: "rgb(var(--accent) / <alpha-value>)",
        },
        sentiment: {
          positive: "rgb(var(--positive) / <alpha-value>)",
          neutral: "rgb(var(--neutral) / <alpha-value>)",
          negative: "rgb(var(--negative) / <alpha-value>)",
        },
        // 來源識別色（source-meta.tsx 改用這組，棄 orange-500/emerald-400 等裸 palette）
        source: {
          hn: "rgb(var(--src-hn) / <alpha-value>)",
          devto: "rgb(var(--src-devto) / <alpha-value>)",
          threads: "rgb(var(--src-threads) / <alpha-value>)",
          ptt: "rgb(var(--src-ptt) / <alpha-value>)",
          lobsters: "rgb(var(--src-lobsters) / <alpha-value>)",
        },
        // （optional）主題 5 類若未來需要色彩編碼：Okabe-Ito 色盲安全子集
        // theme: { tool: "#0072B2", model: "#56B4E9", howto: "#009E73",
        //          risk: "#E69F00", ethics: "#CC79A7" },
      },

      // ── 字級階層：8 階，行高為中文調校（小字越鬆），取代散落的 text-[Npx] ──
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1.5" }],                          // 11px 時間戳/軸標（原 text-[10px]/[11px]）
        xs:    ["0.75rem",   { lineHeight: "1.6" }],                          // 12px 篩選器/輔助（原 text-xs/text-[12px]）
        sm:    ["0.8125rem", { lineHeight: "1.7", letterSpacing: "0.01em" }], // 13px 卡片 snippet（原 text-[13px]）
        base:  ["0.9375rem", { lineHeight: "1.8", letterSpacing: "0.01em" }], // 15px 內文/hero 副標
        md:    ["1.0625rem", { lineHeight: "1.6" }],                          // 17px Section h2（原 text-[17px]）
        lg:    ["1.25rem",   { lineHeight: "1.5" }],                          // 20px 頁標
        xl:    ["1.5rem",    { lineHeight: "1.4" }],                          // 24px hero（行動版）
        "2xl": ["2.125rem",  { lineHeight: "1.3" }],                          // 34px hero（桌面；原 text-[34px] leading-[1.15] → 中文升到 1.3）
      },
      // 卡片標題（text-sm font-medium + line-clamp-2）建議行高 1.5：
      //   <h3 className="text-sm leading-[1.5] ..."> 或為標題加專屬 token

      // ── 字族（CJK fallback 順序修正：Noto 提到 JhengHei 前）──
      fontFamily: {
        sans: ["var(--font-sans)", "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "ui-monospace", "PingFang TC", "Noto Sans TC", "Microsoft JhengHei", "monospace"],
        script: ["var(--font-script)", "Gabriola", "Segoe Script", "Palatino Linotype", "cursive"],
      },

      // ── 圓角/陰影 token 化（值同現況，改名以表意）──
      borderRadius: {
        card: "0.75rem",   // 卡片外殼（= rounded-xl）
        chip: "0.375rem",  // badge / chip（= rounded-md）
        panel: "0.5rem",   // 摘要列 / skeleton（= rounded-lg）
      },
      boxShadow: {
        card: "0 1px 2px 0 rgb(var(--ink) / 0.03)",
        "card-hover": "0 4px 6px -1px rgb(var(--ink) / 0.06), 0 2px 4px -2px rgb(var(--ink) / 0.06)",
      },
    },
  },
};
```

### 4.3 ink 文字層級規範（收斂 10 檔透明度 → 4 檔語意）

| 語意 | 寫法 | 近似對比（白卡上） | 用途 / 規則 |
|---|---|---|---|
| 主文字 | `text-ink` | ~14:1 | 標題、計數 |
| 次文字 | `text-ink/70` | ~5.3:1 ✓AA | snippet、描述——**13px 以下次要文字的底線** |
| 弱文字 | `text-ink/55` | ~3.5:1 | 僅限 ≥18px 或非必要資訊（裝飾性說明） |
| 裝飾 | `text-ink/35` | — | 分隔符、純裝飾，不承載資訊（時間戳要從 /40 升到 /70 或至少加 `title`） |

### 4.4 落地優先序（提案，未動工）

1. **P0（bug）**：`trend-chart.tsx` 白色基準線改 `rgb(var(--ink) / 0.12)`；violet/cyan 線改 accent token。
2. **P0（a11y）**：`source-meta.tsx` 文字色升 `-700` 階（或上面 `source.*` token）；小字 `ink/40 → /70`。
3. **P1**：色彩下沉 CSS 變數 + 字級 8 階置換（純機械替換，`text-[13px] → text-sm` 等）。
4. **P1**：中文排版基建（`text-autospace`/`text-wrap`/`.nums`；中文標題拿掉 `tracking-tight`、原文對照拿掉 `italic`）。
5. **P2**：主題 feed 密集列表形態；local 來源視覺升級。
6. **P3**：UI 字串 Noto Sans TC 微子集（<50KB）；深色模式（變數已就位後成本低）。
