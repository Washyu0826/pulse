import { OTHER_THEME, THEME_ORDER } from "@/components/theme-meta";
import { buildStackedAreas } from "@/lib/trend-path";
import type { ThemeLabel, ThemeTrendPoint } from "@/lib/types";

/**
 * 主題趨勢圖（純 SVG，零依賴，SSR 友善）—— 近 N 天「五大實用主題」逐日貼文數的堆疊面積圖。
 *
 * 與既有 charts/trend-chart 同調：用 lib/trend-path 的純函式算 path（邊界有單元測試），
 * 不引入 recharts（先前 @emnapi 跨平台 npm ci 破壞的教訓）。
 *
 * 設計系統 2 色克制：各主題不各自配色，靠同一寶藍 accent 的「不透明度階」區分堆疊帶，
 * 並以下方圖例（icon + 文字）建立對應 —— a11y 不靠純色傳達資訊。
 */

const W = 720;
const H = 160;
const PAD = 8;

// 同色相不透明度階（深→淺），對應 THEME_ORDER 五主題；維持 2 色系統。
const BAND_OPACITY = [0.85, 0.62, 0.44, 0.28, 0.16] as const;

// 「其他」（低信心 fallback）用中性灰，與五大實用主題的寶藍區隔；仍在 2 色系統內。
// 語料主題偏斜時「其他」常為大宗，必須納入序列/圖例/總數，否則總數少算且整段誤判空狀態。
const OTHER_FILL = "rgb(138 151 172 / 0.45)"; // 對齊 sentiment 中性灰 #8A97AC

// 繪圖順序 = 五大主題 + 其他（6 類），與後端 /api/dashboard/trends 的 6 鍵對齊。
const PLOT_THEMES: readonly ThemeLabel[] = [...THEME_ORDER, OTHER_THEME];
// 各帶的填色：前 5 條走寶藍不透明度階，最後「其他」走中性灰。
const themeFill = (i: number): string =>
  PLOT_THEMES[i] === OTHER_THEME ? OTHER_FILL : `rgb(77 116 234 / ${BAND_OPACITY[i] ?? 0.16})`;

export function ThemeTrendChart({ trend }: { trend: ThemeTrendPoint[] }) {
  if (trend.length === 0) {
    return (
      <div className="card flex h-40 items-center justify-center text-sm text-ink/70">
        這段期間沒有足夠資料畫出主題趨勢。
      </div>
    );
  }

  // 每個主題一條序列（逐日數值）—— 含「其他」共 6 條。
  const series = PLOT_THEMES.map((t) => trend.map((d) => d[t] ?? 0));
  const areas = buildStackedAreas(series, H, { W, PAD });

  const totals = PLOT_THEMES.map((t, i) => ({
    theme: t,
    total: series[i].reduce((a, b) => a + b, 0),
    fill: themeFill(i),
  }));
  const grandTotal = totals.reduce((a, b) => a + b.total, 0);

  const first = trend[0]?.date ?? "";
  const last = trend[trend.length - 1]?.date ?? "";

  return (
    <figure className="card">
      <figcaption className="mb-2 flex items-baseline justify-between">
        <span className="text-xs font-medium text-ink/70">每日主題分布</span>
        <span className="font-mono text-[11px] text-ink/70">
          共 {grandTotal.toLocaleString()} 篇 · 近 {trend.length} 天
        </span>
      </figcaption>
      {grandTotal > 0 ? (
        <svg
          viewBox={`0 0 ${W} ${H}`}
          className="h-40 w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`近 ${trend.length} 天各主題每日貼文數的堆疊面積圖，共 ${grandTotal} 篇`}
        >
          {areas.map((d, i) => (
            <path key={PLOT_THEMES[i]} d={d} fill={themeFill(i)} />
          ))}
        </svg>
      ) : (
        <div className="flex h-40 items-center justify-center text-xs text-ink/70">
          這段期間尚無主題資料。
        </div>
      )}
      <div className="mt-2 flex justify-between px-1 font-mono text-[11px] text-ink/35">
        <span>{first}</span>
        <span>{last}</span>
      </div>
      {/* 圖例：色塊不透明度 + 文字標籤（a11y：不靠純色辨識）。 */}
      <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5 border-t border-border/60 pt-3">
        {totals.map(({ theme, total, fill }) => (
          <li key={theme} className="flex items-center gap-1.5 text-[12px] text-ink/70">
            <span
              aria-hidden
              className="h-2.5 w-2.5 shrink-0 rounded-sm"
              style={{ background: fill }}
            />
            <span>{theme}</span>
            <span className="font-mono text-[11px] tabular-nums text-ink/45">{total.toLocaleString()}</span>
          </li>
        ))}
      </ul>
    </figure>
  );
}

export type { ThemeLabel };
