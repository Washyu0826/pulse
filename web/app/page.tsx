/**
 * Pulse 首頁 - 事件流 + 預設模型即時看板。
 *
 * 這是 Server Component（Next.js 14 預設），在 server 端抓資料。
 * 互動元件（搜尋、即時刷新）會在 Week 2+ 拆出 Client Component。
 */

export default async function HomePage() {
  // TODO Week 2: 從 API 抓真實資料
  // const events = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/events`, {
  //   next: { revalidate: 60 },
  // }).then(r => r.json());

  return (
    <main className="min-h-screen p-8">
      <header className="mb-12">
        <div className="text-xs font-mono tracking-widest text-accent-cyan mb-2">
          DATA PROJECT · LIVE
        </div>
        <h1 className="text-6xl font-bold text-white">Pulse</h1>
        <p className="text-2xl text-white/80 mt-2">AI 工程師的每日情報秘書</p>
        <p className="text-white/50 mt-4 max-w-2xl">
          每天 5 分鐘掌握 AI 圈、不錯過該知道的、需要查時 30 秒給答案。
        </p>
      </header>

      <section className="mb-12">
        <h2 className="text-sm font-mono tracking-widest text-white/50 mb-4">
          ⚡ ACTIVE EVENTS · 過去 6 小時
        </h2>
        <div className="bg-bg-card rounded-xl p-8 border border-border text-center text-white/40">
          {/* TODO Week 2: 接 events API */}
          事件流即將上線（Week 2-5）
        </div>
      </section>

      <section className="mb-12">
        <h2 className="text-sm font-mono tracking-widest text-white/50 mb-4">
          📊 6 模型即時看板
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          {/* TODO Week 2: 接 /api/models */}
          {["GPT-5", "Claude", "Gemini", "Grok", "Llama", "DeepSeek"].map((name) => (
            <div
              key={name}
              className="bg-bg-card rounded-xl p-4 border border-border"
            >
              <div className="text-sm text-white/60">{name}</div>
              <div className="text-2xl font-bold text-white mt-2">--</div>
              <div className="text-xs text-white/40 mt-1">尚未載入</div>
            </div>
          ))}
        </div>
      </section>

      <footer className="mt-16 text-xs font-mono text-white/30">
        PULSE · DATA PROJECT · 冼冠宇 · Xchange
      </footer>
    </main>
  );
}
