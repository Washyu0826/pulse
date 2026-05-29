import { Boxes, Github } from "lucide-react";

import type { ReleaseEvent } from "@/lib/types";

/**
 * 相對時間（zh-TW），用內建 Intl，不加依賴。
 * 注意：在 server render 時計算，靜態頁面下會凍結至下次 revalidate（此處 60s，可接受）。
 */
function relativeTime(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";  // 壞的 published_at → 不顯示，避免 "NaN 天前"
  const diffSec = Math.round((t - Date.now()) / 1000);
  const rtf = new Intl.RelativeTimeFormat("zh-TW", { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
    ["second", 1],
  ];
  for (const [unit, secs] of units) {
    if (Math.abs(diffSec) >= secs || unit === "second") {
      return rtf.format(Math.round(diffSec / secs), unit);
    }
  }
  return "";
}

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
      <div className="flex items-center gap-2 text-xs font-mono text-white/40">
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
