import { buildStackedAreas } from "@/lib/trend-path";
import type { SentimentTrendPoint } from "@/lib/types";

/**
 * 情緒走勢圖（純 SVG，零依賴，SSR 友善）—— 近 N 天逐日「正/中性/負」情緒佔比的堆疊面積圖。
 * 與 charts/trend-chart、theme-trend-chart 同調（lib/trend-path 純函式 + 無 recharts）。
 *
 * 三段用設計系統的 sentiment token（正=寶藍、中性/負=冷灰深淺，仍在 2 色系統內），
 * 並以圖例（色點 + 可見文字標籤）建立對應 —— a11y 不靠純色傳達資訊。
 */

const W = 720;
const H = 140;
const PAD = 8;

const SERIES = [
  { key: "positive" as const, label: "正面", color: "#4D74EA" },
  { key: "neutral" as const, label: "中性", color: "#8A97AC" },
  { key: "negative" as const, label: "負面", color: "#5A6677" },
];

export function SentimentTrendChart({ trend }: { trend: SentimentTrendPoint[] }) {
  if (trend.length === 0) {
    return (
      <div className="card flex h-36 items-center justify-center text-sm text-ink/70">
        這段期間沒有足夠資料畫出情緒走勢。
      </div>
    );
  }

  const series = SERIES.map((s) => trend.map((d) => d[s.key] ?? 0));
  const areas = buildStackedAreas(series, H, { W, PAD });

  const totals = SERIES.map((s, i) => ({ ...s, total: series[i].reduce((a, b) => a + b, 0) }));
  const grandTotal = totals.reduce((a, b) => a + b.total, 0);

  const first = trend[0]?.date ?? "";
  const last = trend[trend.length - 1]?.date ?? "";

  return (
    <figure className="card">
      <figcaption className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium text-ink/70">每日情緒佔比</span>
        <span className="font-mono text-[11px] text-ink/70">
          共 {grandTotal.toLocaleString()} 篇 · 近 {trend.length} 天
        </span>
      </figcaption>
      {grandTotal > 0 ? (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-36 w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`近 ${trend.length} 天逐日正面、中性、負面情緒佔比的堆疊面積圖`}
        >
          {areas.map((d, i) => (
            <path key={SERIES[i].key} d={d} fill={SERIES[i].color} fillOpacity={0.85} />
          ))}
        </svg>
      ) : (
        <div className="flex h-36 items-center justify-center text-xs text-ink/70">
          這段期間尚無情緒資料。
        </div>
      )}
      <div className="mt-2 flex justify-between px-1 font-mono text-[11px] text-ink/35">
        <span>{first}</span>
        <span>{last}</span>
      </div>
      {/* 圖例：色點 + 可見文字標籤（a11y：情緒不靠純色傳達）。 */}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-border/60 pt-3">
        {totals.map(({ key, label, color, total }) => (
          <li key={key} className="flex items-center gap-1.5 text-[12px] text-ink/70">
            <span aria-hidden className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
            <span>{label}</span>
            <span className="font-mono text-[11px] tabular-nums text-ink/45">{total.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}
