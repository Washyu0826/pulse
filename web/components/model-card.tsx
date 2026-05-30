import type { ModelSummary } from "@/lib/types";

/** 單一模型卡：累計討論數 + 近 7 天增量 + 發布數。近期升溫時右上角亮黃點。 */
export function ModelCard({ m }: { m: ModelSummary }) {
  return (
    <div className="card relative">
      {m.spike_severity != null && (
        <span
          role="img"
          aria-label="近期討論升溫"
          title="近期討論升溫（高於平常）"
          className="absolute right-3 top-3 h-1.5 w-1.5 rounded-full bg-sentiment-neutral shadow-[0_0_6px_theme(colors.sentiment.neutral)]"
        />
      )}
      <div className="truncate text-xs font-medium text-white/60">{m.name}</div>
      <div
        title="累計討論貼文數"
        className="mt-2 font-mono text-2xl font-semibold tabular-nums tracking-tight text-white"
      >
        {m.posts_total.toLocaleString()}
      </div>
      <div className="mt-1.5 flex items-center gap-2 font-mono text-[11px]">
        {m.posts_recent > 0 && <span className="text-sentiment-positive">+{m.posts_recent}</span>}
        <span className="text-white/45">近7天</span>
        <span className="ml-auto text-white/45">{m.releases_total} 發布</span>
      </div>
    </div>
  );
}
