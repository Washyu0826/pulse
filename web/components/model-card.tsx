import Link from "next/link";
import { ArrowRight } from "lucide-react";

import type { ModelSummary } from "@/lib/types";

function sentimentClass(idx: number): string {
  return idx > 10 ? "text-sentiment-positive" : idx < -10 ? "text-sentiment-negative" : "text-ink/70";
}

/** 單一模型卡：累計討論數 + 口碑指數 + 近 7 天 + 發布數。整張可點 → 模型詳情頁。 */
export function ModelCard({ m }: { m: ModelSummary }) {
  return (
    <Link
      href={`/models/${m.slug}`}
      aria-label={`查看 ${m.name} 詳情`}
      className="card-interactive group relative block"
    >
      {m.spike_severity != null && (
        <span
          role="img"
          aria-label="近期討論升溫"
          title="近期討論升溫（高於平常）"
          className="absolute right-3 top-3 h-1.5 w-1.5 rounded-full bg-sentiment-neutral shadow-[0_0_6px_theme(colors.sentiment.neutral)]"
        />
      )}
      <div className="truncate text-xs font-medium text-ink/60">{m.name}</div>
      <div
        title="累計討論貼文數"
        className="mt-2 font-mono text-2xl font-semibold tabular-nums tracking-tight text-ink"
      >
        {m.posts_total.toLocaleString()}
      </div>
      {m.sentiment_index != null && (
        <div
          title="口碑淨值（情緒分析，-100..100）：正=多數好評，負=多數負評"
          className={`mt-1 font-mono text-xs ${sentimentClass(m.sentiment_index)}`}
        >
          口碑 {m.sentiment_index > 0 ? `+${m.sentiment_index}` : m.sentiment_index}
          {m.sentiment_index > 10 ? " ↑" : m.sentiment_index < -10 ? " ↓" : ""}
        </div>
      )}
      <div className="mt-1.5 flex items-center gap-2 font-mono text-[11px]">
        {m.posts_recent > 0 && <span className="text-sentiment-positive">+{m.posts_recent}</span>}
        <span className="text-ink/45">近7天</span>
        <span className="ml-auto text-ink/45">{m.releases_total} 發布</span>
      </div>
      <span className="mt-2 flex items-center gap-1 text-[11px] text-ink/0 transition-colors group-hover:text-accent-primary">
        查看詳情 <ArrowRight className="h-3 w-3" aria-hidden />
      </span>
    </Link>
  );
}
