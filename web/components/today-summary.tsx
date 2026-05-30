import { InfoHint } from "@/components/ui/info-hint";
import { getModelDashboard, getRecentEvents } from "@/lib/api";

function Stat({
  value,
  label,
  hint,
}: {
  value: number | string;
  label: string;
  hint?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <span className="font-mono text-2xl font-semibold tabular-nums tracking-tight text-white">
        {value}
      </span>
      <span className="mt-0.5 flex items-center gap-1 text-xs text-white/50">
        {label}
        {hint && <InfoHint label={label}>{hint}</InfoHint>}
      </span>
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
    <div>
      <p className="mb-2 text-xs text-white/45">近 7 天動態</p>
      <div className="grid grid-cols-3 gap-4 rounded-lg border border-border/60 bg-bg-card px-5 py-4">
        <Stat
          value={spikes}
          label="討論突增"
          hint="單日討論量明顯高於平常（穩健統計偵測）。"
        />
        <Stat value={launches} label="新發布" hint="HuggingFace / GitHub 偵測到的新版釋出。" />
        <Stat
          value={`${heating}/${models.data.length}`}
          label="模型升溫中"
          hint="近 7 天討論量高於平常的模型數 / 監測模型總數。"
        />
      </div>
    </div>
  );
}
