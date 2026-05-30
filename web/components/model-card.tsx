import type { ModelSummary } from "@/lib/types";

/** 單一模型看板卡（純展示）。近期有討論突增時右上角亮黃點。 */
export function ModelCard({ m }: { m: ModelSummary }) {
  return (
    <div className="bg-bg-card rounded-xl p-4 border border-border">
      <div className="flex items-center justify-between gap-2">
        <div className="text-sm text-white/60 truncate">{m.name}</div>
        {m.spike_severity != null && (
          <span
            title={`近期討論突增 · severity ${m.spike_severity}`}
            className="w-2 h-2 rounded-full bg-sentiment-neutral shrink-0"
          />
        )}
      </div>
      <div className="text-2xl font-bold text-white mt-2">
        {m.posts_total.toLocaleString()}
      </div>
      <div className="text-xs text-white/50 mt-1 font-mono">
        近7天 +{m.posts_recent} · {m.releases_total} 發布
      </div>
    </div>
  );
}
