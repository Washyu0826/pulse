# UX 研究 02：競品與業界互動模式（2026-06-12）

> 5 個 UIUX 研究 agent 之一：**競品與業界互動模式研究**。
> 與 `docs/competitor-analysis.md` 的分工：那份回答「Pulse 該不該打這場仗」（定位層，結論＝作品集 + N=1 自用）；
> 本文回答「**這些產品的互動細節哪些值得抄**」（UX/互動層）。
> 對照基準：`docs/ux/positioning-c-ux.md` 的 IA（首頁三主題分區 / 主題列表頁 / 查詢頁 / 單篇頁）+ 收藏→知識材料包 + 每日電子報。
>
> 註：任務指定的「探索更多」查無同名台灣產品，台灣在地樣本改以 **InfoAI**（台灣 AI 新聞精選電子報）+ 主流科技媒體（iThome / TechNews / INSIDE）替代。

---

## 第一部分：逐產品分析（7 個）

### 1. TLDR Newsletter（每日科技電子報，160 萬訂閱、46% 開信率）

| 面向 | 做法 |
|------|------|
| 資訊密度 | 極高且**無圖**：每則 = 標題 + 閱讀時間估計 + 2–3 句摘要 + 連結。整封 < 5 分鐘讀完是明示承諾 |
| 今日重點 | 主旨列用 emoji 標記當日頭條；內文固定分區（Big Tech & Startups / Science / Misc），**分區順序每天不變** |
| 篩選/分類 | 無互動篩選（email 載體）；分類靠固定小節，靠「訂閱不同版本」（AI / Web Dev / …）做粗篩 |
| 已讀/收藏 | 無（email 的天生弱點，也是 Readwise 這類工具存在的理由） |
| 行動端 | 純文字單欄，天生行動友善 |

**對 Pulse 的判斷**：
- ✅ **每則標注閱讀時間（或字數）**：成本極低、讓「5 分鐘掃完」從口號變可感知的服務。TLDR 的 46% 開信率很大程度歸功於這種「尊重時間」的訊號。→ 首頁卡片 + 電子報，**P1**。
- ✅ **分區順序固定不動**：positioning-c-ux 已定三主題順序（新工具→使用方法→邊界），要寫成鐵律——每日回訪產品的肌肉記憶比「智慧排序」重要。→ 首頁 + 電子報，**P0（守住既有設計）**。
- ❌ 多版本訂閱分流：Pulse 是 N=1 自用，不需要。

### 2. Perplexity Discover（AI 情報 feed）

| 面向 | 做法 |
|------|------|
| 資訊密度 | 中低：大卡片 + 配圖 + AI 生成摘要，偏雜誌感、casual browsing |
| 今日重點 | 「Top」分頁 + 「For You」個人化聚合；另把 feed 轉成 Discover Daily podcast（TTS 播報） |
| 篩選/分類 | onboarding 選興趣 topic + 語言偏好；頂部 dropdown 切 For You / Tech / Finance / Sports… |
| 已讀/收藏 | 弱；重點在「點卡片 → 進入 AI 整理頁（含引用源）」而非外連原文 |
| 行動端 | 垂直滑動 feed；官方 showcase「Flow & Focus」用垂直滑卡 + 橫向深入面板 |

**對 Pulse 的判斷**：
- ✅ **點卡片先進「自家整理頁」而非直接外連**：Pulse 單篇頁已是這個模式（摘要 + meta + 原文連結），這是正確方向——自訓摘要模型是 Pulse 的技術核心，整理頁就是它的舞台。→ 單篇頁，**P0（守住）**。
- ⚠️ 大圖雜誌卡：與「5 分鐘掃完」目標衝突，Pulse 是工程師工具不是 casual browsing。首頁卡片**不要**加配圖。→ 反面教材。
- ❌ TTS/podcast 化：成本高、N=1 需求未驗證。**P3 以下，不列**。

### 3. Readwise Reader（read-it-later 權威，本題最重要樣本）

| 面向 | 做法 |
|------|------|
| 資訊密度 | 高密度列表（標題 + 來源 + 進度條 + 預估時間），三欄桌面布局 |
| 今日重點 | 不做「今日新聞」，做 **Daily Review**：每天從你的 highlights 抽 5–10 則回顧，2–3 分鐘完成 |
| 篩選/分類 | Inbox / Later / Archive 三段 **triage**（學 Superhuman 的遊戲化清信箱）；強大的 filter query |
| 已讀/收藏 | 核心：highlight 自動同步 → 進入 spaced repetition（半衰期 7/14/28 天的衰減演算法）每日 resurface |
| 行動端 | 手勢 triage（滑左滑右分流）、share sheet 收藏 |

**對 Pulse 的判斷**：
- ✅✅ **「收藏不是終點，是進入回流系統的入口」**：這是 Readwise 與死掉的 Pocket 的本質差異，也直接驗證 Pulse「收藏→知識材料包」的方向正確。但 Readwise 是「每日小量回顧」，Pulse 是「批次打包成材料」——兩者可互補（見第二部分 c 題）。→ 收藏功能，**P0**。
- ✅ **Inbox→處理→Archive 的狀態流**：Pulse 收藏目前是單一桶。最小可行版：收藏列表分「未打包 / 已打包」兩態，打包過的自動歸檔，讓收藏匣維持「待處理」的緊張感而非垃圾場。→ 收藏頁，**P1**。
- ❌ 完整 spaced repetition 演算法：N=1 不需要這個複雜度，用「電子報尾端帶舊收藏」達成 80% 效果（見 c 題）。

### 4. Hacker News 客戶端（hckrnews + Harmonic）

**hckrnews**（網頁版，與 Pulse 場景最像：每天回訪、怕漏掉重點）：

| 面向 | 做法 |
|------|------|
| 資訊密度 | 純列表、按**時間軸**排（非熱度排名），一天一段 |
| 今日重點 | filter 切 **Top 10 / Top 20 / Top 50%**：在時間軸上只顯示達門檻的故事——「完整性」與「只看重點」一鍵切換 |
| 已讀 | **last visit 標記**：標出上次來訪之後的新內容；瀏覽器擴充還標新留言 |
| 補漏 | 「retrieve previous days」往回翻整天，解決「昨天沒開就漏掉」 |

**Harmonic**（Android 客戶端）：Material 設計、Top/Best/New 切換、隱藏 jobs 貼文、bookmark 匯入匯出、可關縮圖（密度自選）。

**對 Pulse 的判斷**：
- ✅✅ **「上次看到這裡」分隔線**：Pulse 的 JTBD 就是每天回訪。在首頁三區內標出「自上次造訪後的新內容」（或卡片上 NEW 點），直接回答「今天有什麼**新的**」而不是「今天 top N 是什麼」。實作成本低（localStorage 記 last_visit 時間戳即可，N=1 不用帳號系統）。→ 首頁，**P0**。
- ✅ **補昨天**：某天沒開 Pulse，隔天能一鍵看「昨天的三主題重點」。查詢頁的 days 參數已能支撐，只差首頁一個「← 昨天」入口。→ 首頁/查詢頁，**P2**。
- ✅ Top N 門檻切換（10/20/50%）：Pulse 對應物是「只看高信心」vs「看全部含其他」，positioning 文件已設計（其他預設收合），方向一致，不用加。

### 5. Feedly / Folo（RSS 閱讀器，新舊兩代）

**Feedly（Leo AI）**：

| 面向 | 做法 |
|------|------|
| 篩選 | Leo 做 prioritize（重點置頂）、**mute**（靜音關鍵字）、**deduplicate**（多源報同一件事自動去重） |
| 密度 | Title-only / Magazine / Cards 多種檢視**讓使用者自選密度** |
| 訓練 | 對 Leo 的判斷給 feedback，越用越準 |

**Folo（開源 AI RSS reader，2024–）**：統一時間軸 + 內建 AI 翻譯/摘要/標籤 + **每日 AI digest**。概念上是 Pulse 最近的開源親戚（差異：Folo 是通用訂閱工具，Pulse 是垂直 AI 情報 + 自訓模型）。

**對 Pulse 的判斷**：
- ✅✅ **去重（同事件多源合併）**：HN 和 Dev.to 常同天報同一件事。Pulse 已有「今日事件摘要」（事件聚合），應該反過來用在 feed 上：同事件的卡片合併成一張、標「3 個來源」。這同時是自家事件聚合技術的展示位。→ 首頁/主題列表頁，**P1**。
- ✅ mute 關鍵字：N=1 自用很實用（例如永久靜音某個一直洗版的工具名），實作簡單。→ 查詢/設定，**P2**。
- ⚠️ 多種檢視密度切換：做一種對的（首頁卡片、列表頁高密度列表）勝過做三種讓使用者選。N=1 不需要偏好設定的維護成本。→ 不做切換，但**列表頁要用高密度列表而非卡片**（見第二部分 a 題），**P1**。
- ❌ feedback 訓練迴圈 UI：模型迭代走離線標註流程即可（已有 gold 標註計畫），不需要做進產品 UI。

### 6. Product Hunt daily digest（The Leaderboard）

| 面向 | 做法 |
|------|------|
| 今日重點 | 每日 **top 10 固定名額**：排名 = 稀缺性 = 「看完就是看完了」的封閉感 |
| 密度 | 每則：名稱 + 一句 tagline + 票數，極短 |
| 分類 | 週日 Roundup（週回顧）、週二 Frontier（AI 專版）——**用「星期幾」做分類**而非版面分區 |

**對 Pulse 的判斷**：
- ✅ **固定名額的封閉感**：positioning 文件「每區 top 4–6 張卡」已是這個精神，這裡補一個強化：首頁頂部「今日摘要列」顯示 `🆕 23 · 🛠️ 11 · 🚧 7` 計數，掃完三區後使用者知道「今天結束了」。**封閉感（finite feed）是對抗 doomscroll 的關鍵差異化**，演算法 feed 做不到。→ 首頁，**P0（守住 + 文案強化）**。
- ✅ 一句話 tagline：Pulse 卡片摘要應壓在 1–2 句（自訓摘要模型的輸出長度約束），不要整段。→ 卡片設計，**P1**。
- ❌ 按星期幾分版：電子報頻率 N=1 不需要拆。

### 7. 台灣在地資訊產品（InfoAI / iThome / TechNews / INSIDE）

| 面向 | 觀察 |
|------|------|
| InfoAI | 台灣 AI 新聞精選 + 電子報。賣點是**決策導向解讀**：「這件事真的會影響我的產業嗎？」——不只報 what，幫你判斷 so what |
| iThome / TechNews | 傳統新聞網格：大量卡片 + 廣告 + 無限往下，資訊密度低、噪音高 |
| 共通 | 繁中科技媒體幾乎都**沒有**互動篩選（主題/時間/來源組合查詢），分類就是頻道頁 |

**對 Pulse 的判斷**：
- ✅ **「so what」一行字**：InfoAI 的決策導向值得抄進卡片層——Pulse 的主題分類本身已是 so what 的一半（這是工具/這是用法/這是坑），若摘要模型能在邊界類輸出「要注意什麼」的句式，價值再上一層。→ 摘要 prompt/卡片，**P2（依賴模型能力）**。
- ✅ 繁中媒體沒有可組合篩選 = Pulse 在地差異化成立（與 competitor-analysis 結論一致），filter 列就是相對台媒的賣點，要放在第一屏。→ 首頁，**P0（守住）**。
- ⚠️ 反面教材：台媒的無限捲動 + 廣告卡混排 = Pulse 要避免的樣子。

---

## 第二部分：三題深挖

### (a) 「每日摘要」的呈現模式（daily digest UX）

業界三種主流結構：

| 模式 | 代表 | 優點 | 缺點 |
|------|------|------|------|
| **主題分區**（固定小節） | TLDR、Pulse 現行設計 | 肌肉記憶、回答「分別有什麼」 | 同事件跨區會重複 |
| **時間軸**（按時序 + 門檻 filter） | hckrnews、Folo | 回答「我上次之後發生什麼」、不漏 | 無結構、需要自己歸納 |
| **排名榜**（固定名額） | Product Hunt Top 10 | 封閉感、看完即完 | 漏掉長尾、名額武斷 |

**卡片 vs 列表**（NN/g 與業界共識）：卡片適合**異質內容 + 探索瀏覽**；列表適合**同質內容 + 高效掃描**。Flipboard（卡）對 Feedly（列）是經典分野。

**Pulse 的合成判斷**：
1. **首頁維持「主題分區 + 區內卡片」**，但每區卡數固定（4–6）＋計數徽章 → 同時拿到分區的結構感和排名榜的封閉感。**P0（守住既有設計）**。
2. **疊上 hckrnews 的時間維度**：卡片 NEW 標記（上次造訪後的新內容）＋「← 昨天」回看。分區回答「有什麼」，NEW 標記回答「哪些是新的」——兩個問題都要答。**P0**。
3. **主題列表頁改高密度列表**（單行：標題 + badges + 時間），不要沿用首頁卡片。列表頁的 job 是窮盡掃描，不是探索。**P1**。
4. 電子報 = TLDR 結構直接抄：三小節固定順序、每則 1–2 句 + 閱讀時間 + 連結、無圖（題圖一張就好）。**P1**。

### (b) 中文閱讀產品的排版慣例

來自繁中排版指南（夏木樂、BFA 簡報、黑暗執行緒、好讀的排版指南）的收斂共識：

| 項目 | 建議值 | 備註 |
|------|--------|------|
| 內文字級 | **16–18px**（正文不小於 16px） | Pulse 是掃描型產品，卡片標題 16–17px、摘要 15–16px 可接受，單篇頁正文必須 ≥17px |
| 行高 | 內文 **1.7**（區間 1.5–1.75）；標題 1.3–1.5 | 中文字方塊滿格、無西文 x-height 留白，行高必須比英文預設（1.5）更鬆。介紹型段落可到 1.75–2.0 |
| 字距 letter-spacing | **0** | 多數指南明確反對加字距（傷閱讀）；若品牌感需要，僅限大標題 +0.02–0.05em |
| 段落 | 段距 margin **1em**、**不縮排**（網頁慣例：以空行分段，非首行縮排） | 標題上 1em / 下 0.6–0.8em |
| 行長 | 每行約 **25–40 個全形字** | 對應 max-width 約 32–36em；單篇頁與材料包預覽必守 |
| 字重 | 標題 600；內文 400，**避免 <300**（中文細字在低解析度會糊） | 與字型自託管（已完成）相關：確認託管字型有 400/600 兩檔 |
| 顏色 | 內文至少深於 #666 | 中文筆畫密，灰字代價比英文高 |
| 中英混排 | 中西文之間留 1/4 em 空隙 | Pulse 卡片大量「中文 + 英文工具名」混排，CSS 用 `text-autospace`（已漸有支援）或寫入空格規範 |

**Pulse 的判斷**：這是**單篇頁、知識材料包輸出、電子報**三處的 P0 驗收項——材料包是「會被反覆讀的長文」，排版不對整個功能的質感就垮。首頁卡片影響較小（短文字）。建議直接把上表寫進前端的 typography token（CSS custom properties），一次定義三處共用。**P0（材料包/單篇頁）、P1（其餘）**。

### (c) 「收藏後再利用」的模式

**問題定性**：read-it-later 是被驗證失敗的類別——Pocket 2025 年關站，社群共識是「Read Later list is a graveyard」：收藏率遠大於回讀率，因為(1)收藏即終點、無任何回流提示 (2)回去看時**收藏當下的 context 已丟失**（為什麼存它？）。

**業界三種解法**：

| 解法 | 代表 | 機制 |
|------|------|------|
| 主動 resurface | **Readwise Daily Review** | 每天抽 5–10 則舊 highlight，spaced repetition（半衰期 7/14/28 天）排程，2–3 分鐘完成 |
| 被動提醒 | Mailist 等 | 每週 email 帶上未讀收藏 |
| 轉化出口 | Readwise→Obsidian 匯出、Perplexity Pages | 收藏不是「待讀」而是「素材」，出口是生成新東西 |

**Pulse 的合成判斷**——Pulse 的「收藏→知識材料包」屬於第三類（轉化出口），這是對的、而且比 Readwise 更進一步（不只回顧、直接產出材料）。但缺另外兩類的補位，建議補三件低成本的事：

1. **收藏時留一句 why**（可選輸入框，預設跳過）：收藏理由是材料包生成時最有價值的 context，也解決「回去看忘了為何存」。材料包 prompt 可直接吃這句。→ 收藏互動，**P1**。
2. **打包提示（nudge）**：收藏匣累積 ≥N 則未打包項目時，首頁/收藏頁出現「你有 12 則未打包收藏，要整理成材料包嗎？」——把 graveyard 的庫存壓力轉成功能入口。→ 收藏頁/首頁，**P1**。
3. **電子報尾端固定一欄「上週收藏回顧」**：列 2–3 則最舊的未打包收藏。借 Readwise Daily Review 的精神但零演算法成本（FIFO 即可），且電子報管線已存在。→ 電子報，**P2**。
4. 收藏狀態二分「未打包/已打包」（見 Readwise 節），打包後自動歸檔。→ 收藏頁，**P1**。

---

## 第三部分：模式清單總表

優先度定義：**P0** = 守住既有設計或下個迭代就做；**P1** = 近期做、成本低收益高；**P2** = 有空再做；列「守住」者表示 positioning-c-ux 已涵蓋、本研究驗證其正確。

| # | 模式 | 來源產品 | 描述 | 適用 Pulse | 優先度 |
|---|------|---------|------|-----------|--------|
| 1 | 固定分區 + 固定順序 | TLDR | 每日小節順序永不變，養成掃讀肌肉記憶 | 首頁三區、電子報 | P0（守住） |
| 2 | 封閉式 feed（固定名額 + 計數） | Product Hunt | top N 看完即完，對抗 doomscroll | 首頁每區 4–6 卡 + 今日摘要列計數 | P0（守住） |
| 3 | 「上次看到這裡」NEW 標記 | hckrnews | last-visit 時間戳標出新內容（localStorage 即可） | 首頁卡片 | **P0** |
| 4 | 點卡片進自家整理頁 | Perplexity Discover | 先看 AI 摘要 + meta 再決定點原文 | 單篇頁 | P0（守住） |
| 5 | 中文排版 token（16–18px / 行高 1.7 / 字距 0 / 行長 ≤40 字 / 字重 ≥400） | 繁中排版指南共識 | 一次定義、三處共用 | 材料包輸出、單篇頁、電子報 | **P0** |
| 6 | 收藏 = 轉化入口而非終點 | Readwise（反例：Pocket） | 收藏必須有出口與回流，否則必成 graveyard | 收藏→材料包（已是此方向） | P0（守住） |
| 7 | 每則閱讀時間/字數估計 | TLDR | 「尊重時間」的可感知訊號 | 首頁卡片、電子報 | P1 |
| 8 | 主題列表頁用高密度列表 | Feedly、NN/g | 窮盡掃描用列表，探索才用卡片 | 主題列表頁 | P1 |
| 9 | 同事件多源去重合併 | Feedly Leo | 同事件卡片合併、標「N 個來源」（用自家事件聚合） | 首頁、主題列表頁 | P1 |
| 10 | 收藏時留一句 why | （graveyard 研究反推） | 收藏理由 = 材料包生成的 context | 收藏互動 + 材料包 prompt | P1 |
| 11 | 打包 nudge（未打包 ≥N 則提示） | Readwise triage 精神 | 庫存壓力轉成功能入口 | 收藏頁、首頁 | P1 |
| 12 | 收藏二態：未打包/已打包 | Readwise Inbox/Archive | 打包後自動歸檔，收藏匣保持「待處理」 | 收藏頁 | P1 |
| 13 | 摘要壓 1–2 句（tagline 化） | Product Hunt、TLDR | 卡片摘要長度約束 | 卡片設計、摘要模型輸出 | P1 |
| 14 | 電子報 = TLDR 結構（三節 + 短摘 + 連結 + 無圖牆） | TLDR | 已驗證的高開信率格式 | 每日電子報 | P1 |
| 15 | 「← 昨天」補漏入口 | hckrnews | 沒開的那天能一鍵回看 | 首頁 → 查詢頁 | P2 |
| 16 | mute 關鍵字 | Feedly Leo | 永久靜音洗版話題 | 查詢/設定 | P2 |
| 17 | 電子報尾端「上週收藏回顧」 | Readwise Daily Review（簡化版） | FIFO 帶 2–3 則未打包收藏 | 每日電子報 | P2 |
| 18 | 邊界類摘要帶「so what」句式 | InfoAI | 不只 what，給「要注意什麼」 | 摘要 prompt（依賴模型能力） | P2 |
| 19 | 大圖雜誌卡、無限捲動、多檢視密度切換、TTS、星期分版、spaced repetition 全演算法 | Perplexity/台媒/Feedly 反面 | 與 5 分鐘掃完或 N=1 成本不符 | — | 不做 |

### 與其他研究 agent 的接口
- #3、#7、#13 影響卡片元件規格 → 給視覺/元件研究。
- #5 排版 token → 給視覺系統研究（與字型自託管成果銜接）。
- #10–#12、#17 是收藏功能的互動增量 → 給收藏/材料包流程研究。

## Sources

- TLDR 格式與開信率：[Readless TLDR review](https://www.readless.app/blog/tldr-newsletter-review-2026)、[Paved: TLDR curation](https://www.paved.com/blog/tldr-newsletter-curation/)、[tldr.tech](https://tldr.tech/)
- Perplexity Discover：[Discover feed 介紹](https://www.firstaimovers.com/p/perplexity-discover-feed)、[Testing Catalog: Discover 改版](https://www.testingcatalog.com/perplexity-plans-web-release-of-updated-discover-feed-with-more-topics/)、[Flow & Focus showcase](https://docs.perplexity.ai/cookbook/showcase/flow-and-focus)
- Readwise：[Reader 官方](https://readwise.io/read)、[Reviewing Highlights docs](https://docs.readwise.io/readwise/docs/faqs/reviewing-highlights)、[Adding Intention to Spaced Repetition](https://blog.readwise.io/adding-intention-to-spaced-repetition/)、[Block 81: Why I Switched](https://block81.com/blog/why-i-switched-to-readwise-and-reader)
- HN 客戶端：[hckrnews about](https://hckrnews.com/about.html)、[Harmonic-HN GitHub](https://github.com/SimonHalvdansson/Harmonic-HN)
- Feedly / Folo：[Feedly AI](https://feedly.com/ai)、[Feedly Leo review](https://ai-productreviews.com/feedly-leo-review/)、[Folo GitHub](https://github.com/RSSNext/Folo)、[Folo Show HN](https://news.ycombinator.com/item?id=46033915)
- Product Hunt：[Newsletters 總覽](https://www.producthunt.com/newsletters)、[The Top 5](https://www.producthunt.com/newsletter/9631-the-top-5)
- 台灣在地：[InfoAI](https://www.infoai.com.tw/)、[iThome](https://www.ithome.com.tw/)、[TechNews](https://technews.tw/)、[INSIDE](https://www.inside.com.tw/)
- 中文排版：[夏木樂：中文 CSS 排版原則指南](https://simular.co/blog/post/2-%E4%B8%AD%E6%96%87-css-%E6%8E%92%E7%89%88%E5%8E%9F%E5%89%87%E6%8C%87%E5%8D%97)、[BFA：十項排版原則](https://www.bfa.com.tw/blog/ten-rules-that-make-articles-better-understood)、[黑暗執行緒：字型大小與行高](https://blog.darkthread.net/blog/font-size-n-line-height/)、[好讀的排版指南](https://deerlight.design/good-guide-to-typography/)
- 卡片 vs 列表：[NN/g: Cards Component](https://www.nngroup.com/articles/cards-component/)、[uxpatterns.dev: Table vs List vs Cards](https://uxpatterns.dev/pattern-guide/table-vs-list-vs-cards)
- Read-later graveyard：[dev.to: Read Later list is a graveyard](https://dev.to/the_nortern_dev/your-read-later-list-is-a-graveyard-it-is-time-to-stop-hoarding-388g)、[Blackmount: Pocket alternative 分析](https://blackmount.ai/articles/pocket-alternative/)、[TechCrunch: Pocket shutting down](https://techcrunch.com/2025/05/27/read-it-later-app-pocket-is-shutting-down-here-are-the-best-alternatives/)
