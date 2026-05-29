# ADR-005：Next.js Server Components 為主

**狀態**：Accepted
**日期**：2026-05-08

## 背景

Next.js 14 App Router 同時支援 Server Components 與 Client Components，要決定預設策略。

## 選項

1. **Server Components 為主 + Client 點綴**：Next.js 14+ 推薦
2. **全 Client Components**：傳統 React 寫法
3. **Pages Router**：舊版 Next.js

## 決定

選 **Server Components 為主 + Client 點綴**。

## 理由

1. **Pulse 大部分頁面是資料展示**：適合 SSR
2. **首屏快**：使用者通勤打開很有感（差 1 秒體驗差很多）
3. **SEO 加分**：未來想被 Google 找到
4. **Bundle 小**：在 server 跑的不打包進 client
5. **業界趨勢**：Vercel、Linear、Notion、ChatGPT 都這樣

## 後果

**好處**
- 首屏 < 1s
- SEO friendly
- 可直接 `await fetch(...)`、`import { db }`

**代價**
- 心智模型新（要分 server / client）
- 互動元件要拆出來標 `"use client"`
- 即時更新要透過 `revalidate` 或 Client Component

## 重要實作原則

- **預設 Server Component**：所有頁面與元件預設不寫 `"use client"`
- **Client 推到 leaf**：互動部分包成小元件，不要整頁變 client
- **fetch 用 next.revalidate**：不要 useEffect + fetch
- **表單用 Server Actions**：不要寫 API endpoint 處理表單
- **shadcn/ui 元件大多是 client**：用了會把所在 component 變 client，注意

## Pulse 各頁建議

| 頁面 | 模式 |
|------|------|
| 首頁 (/) | Server，互動部分（搜尋）拆 Client |
| 模型詳情 (/models/[slug]) | Server |
| 自訂查詢 (/decide) | Client（互動多） |
| 每日快照 (/daily) | Server |
| 對戰比較 (/compare) | 混合 |
