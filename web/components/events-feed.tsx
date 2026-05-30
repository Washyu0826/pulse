import { EventCard } from "@/components/event-card";
import { SectionStatus } from "@/components/section-status";
import { getRecentEvents } from "@/lib/api";
import type { EventType } from "@/lib/types";

/** 事件流（自帶 fetch；Suspense 邊界內串流）。可依事件類型 / 模型過濾。 */
export async function EventsFeed({
  eventType,
  model,
}: {
  eventType?: EventType;
  model?: string;
}) {
  const events = await getRecentEvents(30, { eventType, model });
  if (!events.ok) {
    return <SectionStatus kind="error">無法載入事件流，請確認 API 是否啟動</SectionStatus>;
  }
  if (events.data.length === 0) {
    const filtered = eventType || model;
    return (
      <SectionStatus kind="empty">
        {filtered ? (
          <>此篩選條件下目前沒有事件 —— 試試放寬條件，或選「全部」。</>
        ) : (
          <>
            目前一切平靜 —— 沒有偵測到討論突增、新發布或口碑翻轉。
            <br />
            有變化時，這裡會自動冒出卡片告訴你發生了什麼、為什麼。
          </>
        )}
      </SectionStatus>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {events.data.map((ev) => (
        <EventCard key={ev.id} ev={ev} />
      ))}
    </div>
  );
}
