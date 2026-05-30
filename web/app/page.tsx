/**
 * Pulse 首頁 - 發布事件流 + 預設模型即時看板。
 *
 * 這是 Server Component（Next.js 14 預設），在 server 端抓資料。
 * 互動元件（搜尋、即時刷新）會在後續拆出 Client Component。
 */
import { getModelDashboard, getRecentEvents, getRecentReleases } from "@/lib/api";
import { EventCard } from "@/components/event-card";
import { ModelCard } from "@/components/model-card";
import { ReleaseCard } from "@/components/release-card";
import { SectionStatus } from "@/components/section-status";

export default async function HomePage() {
  // 三個獨立 fetch 並行；任一失敗都只影響自己的區塊（wrapper 不 throw）。
  const [events, releases, models] = await Promise.all([
    getRecentEvents(15),
    getRecentReleases(20),
    getModelDashboard(),
  ]);

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
          ⚡ 事件流 · 偵測到的突增與發布（F8）
        </h2>
        {!events.ok ? (
          <SectionStatus kind="error">無法載入事件流，請確認 API 是否啟動</SectionStatus>
        ) : events.data.length === 0 ? (
          <SectionStatus kind="empty">目前沒有偵測到事件</SectionStatus>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {events.data.map((ev) => (
              <EventCard key={ev.id} ev={ev} />
            ))}
          </div>
        )}
      </section>

      <section className="mb-12">
        <h2 className="text-sm font-mono tracking-widest text-white/50 mb-4">
          🚀 最新發布事件 · HuggingFace + GitHub
        </h2>
        {!releases.ok ? (
          <SectionStatus kind="error">無法載入發布事件，請確認 API 是否啟動</SectionStatus>
        ) : releases.data.length === 0 ? (
          <SectionStatus kind="empty">目前沒有新的 release 事件</SectionStatus>
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {releases.data.map((ev) => (
              <ReleaseCard key={ev.id} ev={ev} />
            ))}
          </div>
        )}
      </section>

      <section className="mb-12">
        <h2 className="text-sm font-mono tracking-widest text-white/50 mb-4">
          📊 6 模型即時看板
        </h2>
        {!models.ok ? (
          <SectionStatus kind="error">無法載入模型看板，請確認 API 是否啟動</SectionStatus>
        ) : models.data.length === 0 ? (
          <SectionStatus kind="empty">尚無模型資料</SectionStatus>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
            {models.data.map((m) => (
              <ModelCard key={m.slug} m={m} />
            ))}
          </div>
        )}
      </section>

      <footer className="mt-16 text-xs font-mono text-white/30">
        PULSE · DATA PROJECT · 冼冠宇 · Xchange
      </footer>
    </main>
  );
}
