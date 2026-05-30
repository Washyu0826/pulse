import { Activity, Rocket } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/time";
import type { DetectedEvent, EventType } from "@/lib/types";

const TYPE_META: Record<EventType, { label: string; Icon: typeof Activity; color: string }> = {
  discussion_spike: { label: "討論突增", Icon: Activity, color: "text-sentiment-neutral" },
  launch: { label: "發布", Icon: Rocket, color: "text-accent-cyan" },
};

/** 單筆偵測事件卡片（純展示，Server Component）。 */
export function EventCard({ ev }: { ev: DetectedEvent }) {
  const meta = TYPE_META[ev.event_type] ?? TYPE_META.launch;
  const Icon = meta.Icon;
  return (
    <div className="card">
      <div className="flex items-center gap-2">
        <Icon aria-hidden className={`h-3.5 w-3.5 shrink-0 ${meta.color}`} />
        <Badge variant={ev.event_type === "discussion_spike" ? "warn" : "neutral"}>
          {meta.label}
        </Badge>
        {ev.model && <Badge variant="accent">{ev.model}</Badge>}
        {ev.event_type === "discussion_spike" && ev.score != null && (
          <Badge variant="warn">sev {ev.score}</Badge>
        )}
        <time className="ml-auto shrink-0 font-mono text-xs text-white/45">
          {relativeTime(ev.occurred_at)}
        </time>
      </div>
      <h3 className="mt-2.5 text-sm font-medium leading-snug text-white">{ev.title}</h3>
      {ev.description && (
        <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-white/60">
          {ev.description}
        </p>
      )}
    </div>
  );
}
