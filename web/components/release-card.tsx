import { Boxes, Github } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/time";
import type { ReleaseEvent } from "@/lib/types";

const SOURCE_LABEL: Record<ReleaseEvent["source"], string> = {
  github: "GitHub",
  huggingface: "HF",
};

/** 單筆 release 事件卡片（可點擊外連，純展示）。 */
export function ReleaseCard({ ev }: { ev: ReleaseEvent }) {
  const Icon = ev.source === "github" ? Github : Boxes;
  return (
    <a
      href={ev.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={ev.title}
      className="card-interactive group block"
    >
      <div className="flex items-center gap-2">
        <Badge variant="neutral">
          <Icon aria-hidden className="h-3 w-3" />
          {SOURCE_LABEL[ev.source]}
        </Badge>
        {ev.model && <Badge variant="accent">{ev.model}</Badge>}
        {ev.version && <Badge variant="cyan">{ev.version}</Badge>}
        <time className="ml-auto shrink-0 font-mono text-xs text-ink/45">
          {relativeTime(ev.published_at)}
        </time>
      </div>
      <h3 className="mt-2.5 truncate text-sm font-medium text-ink">{ev.title}</h3>
      <p className="mt-1 truncate font-mono text-xs text-ink/45">{ev.repo}</p>
    </a>
  );
}
