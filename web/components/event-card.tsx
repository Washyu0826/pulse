import { Activity, Rocket } from "lucide-react";

import { relativeTime } from "@/lib/time";
import type { DetectedEvent, EventType } from "@/lib/types";

const TYPE_META: Record<EventType, { label: string; Icon: typeof Activity; color: string }> = {
  discussion_spike: { label: "討論突增", Icon: Activity, color: "text-sentiment-neutral" },
  launch: { label: "發布", Icon: Rocket, color: "text-accent-cyan" },
};

/** 單筆偵測事件卡片（純展示，Server Component）。事件無單一外連 → 用 div。 */
export function EventCard({ ev }: { ev: DetectedEvent }) {
  const meta = TYPE_META[ev.event_type] ?? TYPE_META.launch;
  const Icon = meta.Icon;
  return (
    <div className="bg-bg-card rounded-xl p-4 border border-border">
      <div className="flex items-center gap-2 text-xs font-mono text-white/50">
        <Icon aria-hidden className={`w-3.5 h-3.5 shrink-0 ${meta.color}`} />
        <span className={`uppercase tracking-widest ${meta.color}`}>{meta.label}</span>
        {ev.model && <span className="text-accent-primary uppercase">{ev.model}</span>}
        {ev.event_type === "discussion_spike" && ev.score != null && (
          <span className="text-sentiment-neutral">severity {ev.score}</span>
        )}
        <span className="ml-auto shrink-0">{relativeTime(ev.occurred_at)}</span>
      </div>
      <div className="mt-2 text-white font-medium">{ev.title}</div>
      {ev.description && (
        <div className="mt-1 text-sm text-white/50 truncate">{ev.description}</div>
      )}
    </div>
  );
}
