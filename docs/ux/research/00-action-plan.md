# Pulse UIUX 行動方案（五份研究彙整）

> 彙整自 01-audit / 02-patterns / 03-ia-flows / 04-visual-system / 05-mobile-a11y-perf（2026-06-12，5 個研究 agent 並行產出）。
> 優先序原則：**先修斷掉的（P0 功能 bug）→ 再接旅程斷點（P1）→ 再上質感（P2）→ 結構性大改最後（P3）**。
> 設計 token 與元件視覺的落地樣式，見 claude.ai/design「Pulse Design System」專案（design-system/ 目錄同步）。

## P0 — 功能性 bug：核心價值現在是壞的（先修，半天內可全清）

| # | 問題 | 位置 | 來源 |
|---|------|------|------|
| 1 | **後端 feed 仍是舊 3 主題（含「邊界」），前端已 5 主題** → 首頁 5 欄有 3 欄永遠空、邊界資料整包被丟 | `api/api/services/feed.py:22`、`routers/feed.py:21` vs `web/components/theme-meta.tsx:22` | 01 |
| 2 | **來源篩選選 PTT 直接 422**：前端 SOURCE_ORDER 含 ptt、後端 Source Literal 沒有 | `api` feed router | 01 |
| 3 | **API 預設埠 8000 vs 實際 8010**，web/ 無 .env → 開箱全站錯誤 | `web/lib/utils.ts:15` | 01 |
| 4 | 趨勢圖**白色基準線畫在白卡上＝隱形**（暗色殘留）+ violet/cyan 硬編碼破壞 2 色系統 | `web/components/charts/trend-chart.tsx:97` | 04+05 |
| 5 | 決策報告提交鈕 `text-ink` 壓寶藍底（應 `text-white`，對比不足） | `web/app/decide/page.tsx:105` | 01+05 |
| 6 | fetch 全無 timeout（API 不通時 >90s 無回應） | `web/lib/api.ts`、`lib/pack.ts` | 01 |

## P1 — 旅程斷點與行動端硬傷（核心體驗，1–2 天）

**旅程修復（03 案 A，推薦小改不大改）**
- 補 `/theme/[label]` 路由 + 每欄「看全部 →」：主題旅程從「第 4 則之後無路可走」變 1 點直達。每欄硬上限 `getFeed(filters, 4)` 同步處理。
- **今日事件卡可收藏**：♥ 目前只在 FeedCard；事件摘要是產品差異化核心，必須能進收藏→材料包流。
- 材料包生成結果持久化（localStorage，現在重整即丟）+ 生成後「下一步」引導。
- 電子報前端入口（目前 grep 零命中）：`/newsletter` 頁 + 導覽項。
- 導覽改四項：今日 / 主題▾ / 我的最愛 / 電子報；「儀表板」命名退役。
- filter `router.replace` → `push`（可後退，符合 page.tsx 註解原意）；模型頁 BackLink 不要寫死 `/`。

**行動端硬傷（05 前 10）**
- select/input 字級全部 ≥16px（修 iOS 聚焦自動縮放）。
- Header ≤375px 溢出：精簡導覽（設計系統有提案樣式）。
- 收藏愛心 ≥44px 點擊區、脫離整卡外連結疊層（手機按不準直接彈去 Threads）。
- 對比度批次修正：來源徽章 `-400/-500` → `-700` 階（04 有對照表）、`text-ink/55→/70`、時間戳 `/40→/60`、愛心 `/25` 提高。
- 篩選 chips / 引註 [1] 等觸控目標 ≥44px。

**每日回訪體驗（02 P0）**
- 「上次看到這裡」NEW 標記：localStorage 記 last-visit，分區回答「有什麼」+ NEW 回答「哪些是新的」。
- 錯誤文案改使用者語言（4 處「請確認 API 是否啟動」）+ API 掛時四種降級行為統一；「今日事件」API 失敗不要偽裝成「尚無事件」。

## P2 — 質感與打磨（設計系統落地，2–3 天）

- **設計 token 落地**（04 提案，預覽見 Claude Design）：色彩下沉 CSS 變數（深色模式只換變數）、字級收斂 8 階（任意值 `text-[11px]`×13 處清掉）、ink 透明度 10 檔收斂 4 檔語意層。
- **中文排版 token**：內文 16–18px、行高 1.7（現況 1.625 偏緊）、中文標題移除 `tracking-tight`、行長 ≤40 全形字、中文夾數字 `tabular-nums` 取代 `font-mono`。優先套用在**知識材料包長文**（會被反覆讀，質感標竿）、單篇、電子報三處共用。不上全量中文 webfont（04 結論）。
- 收藏時留一句 why（直接餵材料包蒸餾 prompt）+ 收藏二態（未打包/已打包）+ 未打包 ≥N 則 nudge（02 P1）。
- 死碼清理：`how-to-use`、`model-board`、`events-feed`、`releases-feed` 等 7 個無引用元件（01/03/05 三方確認）。
- 行動單欄次序：模型側欄移到情報後；五主題長捲動加錨點。
- 情緒語意補文字標籤（現在只有色點+title，觸控/讀屏都拿不到）。
- PWA 補完：192/512 PNG icon、service worker（離線至少給友善頁）。
- onboarding：首訪一次性引導（收藏→材料包的發現性現在＝0）。

## P3 — 結構性（視 P1/P2 成效再議）

- IA 案 B「今日 / 圖書館 / 工作台」三層重構（03 有遷移路徑）。
- 深色模式（P2 色彩變數化之後成本大降；目前 `darkMode:"class"` 是空殼）。
- `/query`、`/post/[id]` 等定位文件規劃但未建的頁。

## 明確不做（02 有理由）

無限捲動、大圖雜誌卡、多檢視密度切換、TTS、完整 spaced repetition——與「5 分鐘掃完」定位或 N=1 維護成本不符。

## 被研究驗證「做對了、要守住」的

固定三區順序、封閉式 top N + 計數、點卡片進自家摘要頁、「冷墨+單一寶藍」克制視覺、情緒不用紅綠、主題同色+icon 形狀（色盲安全）、Server Component 首屏極輕、收藏→材料包的「轉化出口」方向（業界 Read-Later=graveyard 共識的正解）。
