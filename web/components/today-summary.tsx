import { getModelDashboard, getRecentEvents } from "@/lib/api";

function Stat({ value, label }: { value: number | string; label: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-mono text-2xl font-semibold tabular-nums tracking-tight text-white">
        {value}
      </span>
      <span className="mt-0.5 text-xs text-white/50">{label}</span>
    </div>
  );
}

/** 頂部「近 7 天動態」摘要列 —— 先給答案，再看細節。資料抓不到就不顯示。
 *  三個數字統一用「近 7 天」窗口，與模型看板的「升溫中」一致（避免窗口不一造成誤解）。 */
export async function TodaySummary() {
  const [events, models] = await Promise.all([getRecentEvents(100), getModelDashboard()]);
  if (!events.ok || !models.ok) return null;

  const cutoff = Date.now() - 7 * 86400_000;
  const recent = events.data.filter((e) => new Date(e.occurred_at).getTime() >= cutoff);
  const spikes = recent.filter((e) => e.event_type === "discussion_spike").length;
  const launches = recent.filter((e) => e.event_type === "launch").length;
  const heating = models.data.filter((m) => m.spike_severity != null).length;

  return (
    <div className="grid grid-cols-3 gap-4 rounded-lg border border-border/60 bg-bg-card px-5 py-4">
      <Stat value={spikes} label="近 7 天討論突增" />
      <Stat value={launches} label="近 7 天新發布" />
      <Stat value={`${heating}/${models.data.length}`} label="模型討論升溫中" />
    </div>
  );
}
