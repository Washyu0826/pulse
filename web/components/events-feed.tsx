import { EventCard } from "@/components/event-card";
import { SectionStatus } from "@/components/section-status";
import { getRecentEvents } from "@/lib/api";

/** 事件流（自帶 fetch；Suspense 邊界內串流）。 */
export async function EventsFeed() {
  const events = await getRecentEvents(15);
  if (!events.ok) {
    return <SectionStatus kind="error">無法載入事件流，請確認 API 是否啟動</SectionStatus>;
  }
  if (events.data.length === 0) {
    return <SectionStatus kind="empty">目前沒有偵測到事件</SectionStatus>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {events.data.map((ev) => (
        <EventCard key={ev.id} ev={ev} />
      ))}
    </div>
  );
}
