import { SOURCE_META, SOURCE_ORDER } from "@/components/source-meta";
import { THEME_META, THEME_ORDER } from "@/components/theme-meta";
import { getFeedSummary } from "@/lib/api";
import type { FeedFilters } from "@/lib/types";

/** 今日摘要列：各主題在當前篩選下的貼文數（自帶 fetch）。 */
export async function FeedSummary({ filters }: { filters: FeedFilters }) {
  const summary = await getFeedSummary(filters);
  if (!summary.ok) return null; // 摘要列非關鍵，失敗就不顯示
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-2 rounded-lg border border-border/60 bg-bg-card/40 px-4 py-3">
      {THEME_ORDER.map((t) => {
        const m = THEME_META[t];
        return (
          <div key={t} className="flex items-center gap-1.5">
            <m.Icon className={`h-3.5 w-3.5 ${m.text}`} />
            <span className="text-[13px] text-ink/55">{t}</span>
            <span className="font-mono text-sm font-semibold text-ink">{summary.data[t] ?? 0}</span>
          </div>
        );
      })}
      <span className="ml-auto text-[12px] text-ink/35">
        來自 {SOURCE_ORDER.map((s) => SOURCE_META[s].label).join(" / ")}
      </span>
    </div>
  );
}
