# Pulse Web

Next.js 14 App Router + Server Components 為主的前端。

## 開發

```bash
npm install
npm run dev
# http://localhost:3000
```

## 架構

```
web/
├── app/
│   ├── layout.tsx      根 layout
│   ├── page.tsx        首頁（事件流 + 模型看板 + 怎麼用引導 + 事件篩選）
│   ├── decide/         決策報告頁（資料驅動模型比較）
│   ├── models/[slug]/  模型詳情頁（趨勢圖 + 事件 + 熱門討論 + 發布）
│   └── globals.css
├── components/
│   ├── ui/             shadcn/ui 元件
│   └── (custom)        自訂元件
└── lib/                工具函式
```

## 重要原則

### Server Components 為主，Client 為輔

**預設**：所有 component 都是 Server Component，可以直接 `await fetch(...)`。

**只在需要時加 `"use client"`**：
- 用 hooks（useState、useEffect）
- 處理 onClick、onChange
- 用瀏覽器 API（localStorage 等）

### 資料抓取

```tsx
// ✅ Server Component（預設）
async function Page() {
  const events = await fetch(`${API_URL}/api/events`, {
    next: { revalidate: 60 }, // 60 秒快取
  }).then(r => r.json());
  return <EventList events={events} />;
}
```

### 互動元件

```tsx
// components/SearchBar.tsx
"use client";

export function SearchBar() {
  const [query, setQuery] = useState("");
  // ...
}
```

### 設計系統色票（Tailwind 自訂）

- `bg-bg` — 主背景 #0A0F1E
- `bg-bg-card` — 卡片背景 #151B2D
- `border-border` — 邊框 #2A3149
- `text-accent-primary` — 紫 #8B5CF6
- `text-accent-cyan` — 青 #06B6D4
- `text-sentiment-positive` / `negative` / `neutral`

## 環境變數

```
NEXT_PUBLIC_API_URL=http://localhost:8000  # API endpoint
```

## shadcn/ui 加元件

```bash
npx shadcn-ui@latest init
npx shadcn-ui@latest add button card dialog
```
