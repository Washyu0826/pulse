import type { ModelSummary } from "@/lib/types";

/** 單一模型 stat 卡（大數字 + 近 7 天 delta + 發布數）。近期突增右上角亮黃點。 */
export function ModelCard({ m }: { m: ModelSummary }) {
  return (
    <div className="card relative">
      {m.spike_severity != null && (
        <span
          title={`近期討論突增 · severity ${m.spike_severity}`}
          className="absolute right-3 top-3 h-1.5 w-1.5 rounded-full bg-sentiment-neutral shadow-[0_0_6px_theme(colors.sentiment.neutral)]"
        />
      )}
      <div className="truncate text-xs font-medium text-white/60">{m.name}</div>
      <div className="mt-2 font-mono text-2xl font-semibold tabular-nums tracking-tight text-white">
        {m.posts_total.toLocaleString()}
      </div>
      <div className="mt-1.5 flex items-center gap-2 font-mono text-[11px]">
        {m.posts_recent > 0 && <span className="text-sentiment-positive">+{m.posts_recent}</span>}
        <span className="text-white/40">7d</span>
        <span className="ml-auto text-white/40">{m.releases_total} rel</span>
      </div>
    </div>
  );
}
