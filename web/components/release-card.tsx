import { Boxes, Github } from "lucide-react";

import { relativeTime } from "@/lib/time";
import type { ReleaseEvent } from "@/lib/types";

const SOURCE_LABEL: Record<ReleaseEvent["source"], string> = {
  github: "GITHUB",
  huggingface: "HUGGING FACE",
};

/** 單筆 release 事件卡片（純展示，Server Component）。 */
export function ReleaseCard({ ev }: { ev: ReleaseEvent }) {
  const Icon = ev.source === "github" ? Github : Boxes;
  return (
    <a
      href={ev.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block bg-bg-card hover:bg-bg-cardLight rounded-xl p-4 border border-border transition-colors"
    >
      <div className="flex items-center gap-2 text-xs font-mono text-white/50">
        <Icon aria-hidden className="w-3.5 h-3.5 shrink-0" />
        <span className="uppercase tracking-widest">{SOURCE_LABEL[ev.source]}</span>
        {ev.model && (
          <span className="text-accent-primary uppercase">{ev.model}</span>
        )}
        {ev.version && <span className="text-accent-cyan">{ev.version}</span>}
        <span className="ml-auto shrink-0">{relativeTime(ev.published_at)}</span>
      </div>
      <div className="mt-2 text-white font-medium truncate">{ev.title}</div>
      <div className="mt-1 text-sm text-white/50 font-mono truncate">{ev.repo}</div>
    </a>
  );
}
