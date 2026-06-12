# Pulse 設計系統預覽集

> 由 5 份 UIUX 研究（`docs/ux/research/01–05`）收斂而成的視覺規格。每個 HTML 完全自包含
>（inline CSS、零外部資源、零 webfont——中文走系統字 stack），離線雙擊即可開。
> 定位是**演進不是推翻**：保留「冷墨 ink ＋ 單一寶藍、2 色克制、情緒不用紅綠」的既有識別。

## 檔案結構

| 檔案 | @dsCard group | 內容 |
|---|---|---|
| `foundations/colors.html` | 色彩 | ink 4 檔語意層、寶藍主色階（含新 accent-strong）、表面色 |
| `foundations/semantic-colors.html` | 色彩 | 主題 5+1（同色＋形狀）、情緒 4 態（無紅綠）、來源 -700 修正對照 |
| `foundations/typography.html` | 字級 | 中文字級 8 階、長文 17px/1.75 基準、tracking 與 tabular-nums 示範 |
| `foundations/spacing.html` | 基礎 | 4px 間距尺度、圓角三檔、陰影兩檔、44px 觸控規格 |
| `components/buttons.html` | 元件 | primary/secondary/ghost × default/hover/disabled，44px、白字修正 |
| `components/source-badges.html` | 元件 | 五來源全套＋修正前後對比值、「在地」標、emoji→圓點 |
| `components/theme-chips.html` | 元件 | 5 主題＋其他，選中態，44px 觸控 |
| `components/favorite-button.html` | 元件 | 收藏三態（未收藏/已收藏/已打包）＋「不疊在整卡連結上」佈局 |
| `components/filter-bar.html` | 元件 | 16px 表單控制項（修 iOS zoom）、375px 折行示範 |
| `components/feed-card.html` | 卡片 | FeedCard 改良版（NEW 標記、情緒點＋文字、動作列） |
| `components/event-card.html` | 卡片 | 今日事件卡：忠實摘要＋觸控友善引註 [1][2]＋出處列 |
| `patterns/states.html` | 狀態 | 空/錯誤/載入三態＋文案修正對照表 |
| `patterns/mobile-header.html` | 版型 | ≤375px Header 兩案：精簡頂列／底部 tab bar（safe-area） |
| `patterns/longform-reading.html` | 版型 | 知識材料包長文版式（17px/1.75/行長≤40字） |
| `patterns/today-layout.html` | 版型 | 「今日」首屏縮影：事件置頂＋NEW 分隔線＋三區順序 |

## Token 速覽

```
色彩    ink #1B2536 · ink/70（次）· ink/55（限大字）· ink/35（裝飾）
        accent #4D74EA（品牌/圖形/大字）· accent-strong #385CCC（小字/按鈕底，白字 5.9:1）
        accent-deep #2E4DAD（hover）· accent/10 底 · accent/30 框
表面    bg #F4F7FC · card #FFFFFF · hover #EAF1FB · border #D9E2F1
情緒    正 #4D74EA 實心 · 中 #8A97AC 實心 · 負 #5A6677 空心 · 未分析 虛線（一律帶文字標籤）
來源    文字 -700：HN #C2410C · Dev.to #6D28D9 · Threads #385CCC · PTT #047857 · Lobsters #B91C1C
字級    11/12/13/15/17/20/24/34 八階；行高 1.5–1.8（中文調校）；長文 17px/1.75/36em
圓角    chip 6 · panel 8 · card 12        陰影  0 1px 2px ink/5% · hover 0 6px 16px ink/8%
觸控    一律 ≥44×44px、相鄰間距 ≥8px      表單  font-size ≥16px（iOS zoom）
```

## 與 `web/` 現況的差異清單（落地時要改的東西）

### 色彩（`tailwind.config.ts`、`globals.css`）
1. **色值下沉 CSS 變數**：現況 hex 寫死在 Tailwind config → 改 `rgb(var(--x) / <alpha-value>)`，深色模式只要換變數值。
2. **新增 `accent-strong #385CCC`／`accent-deep #2E4DAD`**：小字 accent 文字與按鈕底改用 strong（#4D74EA 白底僅 4.2:1）。
3. **ink 透明度 10 檔 → 4 檔語意**：次要文字底線從 `ink/40~/55` 升到 `ink/70`；`/55` 只准 ≥18px；`/35` 純裝飾。時間戳由 `ink/40` 升 `ink/70`。
4. **來源徽章文字色 `-400/-500` → `-700`**（`source-meta.tsx`）：HN orange-700、Dev.to violet-700、PTT emerald-700、Lobsters red-700、Threads accent-strong；底/框維持 `-500/10`、`-500/30`。
5. **`accent-cyan`/`accent-pink` 舊別名**：過渡保留指向 primary，元件改完即刪。

### 字級／排版
6. **字級 8 階 token 取代任意值**：`text-[10px]`（廢止，最小 11px）、`text-[11px]`×13、`text-[13px]`×12 等全數機械替換。
7. **行高中文化**：snippet `leading-relaxed(1.625)` → 1.7；卡片標題 1.375 → 1.5；hero `leading-[1.15]` → 1.3。
8. **中文標題拿掉 `tracking-tight`**；中文 Badge 拿掉 `uppercase tracking-wider`。
9. **原文對照拿掉 `italic`**（`feed-card.tsx:57`）：中文假斜難看，改降階＋降色。
10. **中文夾數字不用 `font-mono`**（`event-card.tsx:56` 等）：改 `font-sans` + `.nums`（tabular-nums）。
11. **字族順序**：`Noto Sans TC` 提到 `Microsoft JhengHei` 前面。
12. **新增漸進增強**：`:lang(zh-Hant){ text-autospace; text-spacing-trim }`、`h1,h2{text-wrap:balance}`、body `overflow-wrap:break-word`。

### 元件
13. **按鈕抽成單一元件**：統一 `bg-accent-strong text-white`、44px、16px；修 `decide/page.tsx:105` 的 `text-ink` 壓寶藍（2:1）筆誤。
14. **來源徽章去 emoji**：改 currentColor 圓點；字級 10px → 11px；Threads/PTT 加「在地」實心標（寫進 aria-label）。
15. **情緒點加文字標籤＋形狀差異**：負面改空心、未分析虛線空心；篩選器的 🟢🔴 emoji 改 ●/◌（修紅綠語彙矛盾）。
16. **收藏鈕**：`ink/25`(1.7:1) → `ink/70`；24px → 44px 命中區；**移出整卡 stretched link**，改卡底獨立動作列；新增第三態「已打包」（打包後自動歸檔）。
17. **篩選 select/input 16px**（修 iOS 聚焦縮放）、chips 26px → 44px。
18. **FeedCard 新增**：NEW 標記（localStorage last-visit）、閱讀時間估計、aria-label 用 `title_zh ?? title`。
19. **事件摘要引註 [n]**：10px 上標 → ≥24px 膠囊；出處列每行 44px。

### 版型／狀態
20. **行動版 Header**：≤375px 溢出 → 精簡頂列或底部 tab bar（＋safe-area）；「Live」恆亮 → 「更新於 HH:MM」；導覽用語「儀表板→今日」。
21. **錯誤文案去開發者化**：「請確認 API 是否啟動」→「資料暫時載入不了」；錯誤與空狀態分開；次要區故障降級 placeholder 而非消失。
22. **每主題區加「看全部 (N) →」**（修 IA 斷頭）；「今日」label → 「近 24 小時」。
23. **材料包輸出套長文版式**：17px/1.75/36em/段距 1em——目前 `<pre>` 11px mono 預覽不符「會被反覆讀」的定位。

### 沿用不變（守住）
- 2 色克制、情緒不用紅綠、主題同色＋icon 形狀、卡片 `p-5`/`rounded-xl`/雙檔陰影、
  Suspense 骨架、`prefers-reduced-motion`、focus-visible ring、絕不 throw 的資料層。
