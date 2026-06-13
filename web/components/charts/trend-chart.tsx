import { buildPath, buildSentimentPath } from "@/lib/trend-path";
import type { TrendPoint } from "@/lib/types";

/**
 * 趨勢圖（純 SVG，零依賴）—— 上：逐日討論量面積圖；下：逐日口碑折線（-100..100）。
 *
 * 為何不用 recharts：先前 recharts 的 package-lock 帶進 @emnapi 平台相依，
 * 在 Linux CI 上 `npm ci` 會缺檔而中斷（cross-platform 破壞）。這個需求只要一條
 * 趨勢線，用 SVG 畫即可——無新依賴、SSR 友善、不影響 package-lock。
 *
 * path 幾何計算抽到 lib/trend-path.ts（純函式），邊界情況（0/1 點、全 NaN）有單元測試。
 */

const W = 720;
const VOL_H = 120;
const SENT_H = 80;
const PAD = 8;
const GEOM = { W, PAD };

export function TrendChart({ trend }: { trend: TrendPoint[] }) {
  if (trend.length === 0) {
    return (
      <div className="card flex h-40 items-center justify-center text-sm text-ink/70">
        這段期間沒有足夠資料畫出趨勢。
      </div>
    );
  }

  const posts = trend.map((p) => p.posts);
  const maxPosts = Math.max(1, ...posts);
  const totalPosts = posts.reduce((a, b) => a + b, 0);
  const { area, line } = buildPath(posts, VOL_H, maxPosts, GEOM);

  // 口碑：把 -100..100 映到 0..1 的 y（0 = 中性基準線）。只連有資料的點。
  const sentVals = trend.map((p) => p.sentiment_index);
  const hasSent = sentVals.some((v) => v != null);
  const sentLine = buildSentimentPath(sentVals, SENT_H, GEOM);

  const first = trend[0]?.date ?? "";
  const last = trend[trend.length - 1]?.date ?? "";

  return (
    <div className="space-y-4">
      <figure className="card">
        <figcaption className="mb-2 flex items-baseline justify-between">
          <span className="text-xs font-medium text-ink/70">每日討論量</span>
          <span className="font-mono text-[11px] text-ink/70">
            共 {totalPosts.toLocaleString()} 篇 · 單日最高 {maxPosts}
          </span>
        </figcaption>
        <svg
          viewBox={`0 0 ${W} ${VOL_H}`}
          className="h-32 w-full"
          preserveAspectRatio="none"
          role="img"
          aria-label={`每日討論量趨勢，共 ${totalPosts} 篇`}
        >
          {/* 2 色系統：討論量走寶藍 accent（#4D74EA），不再用暗色主題殘留的 violet。 */}
          <path d={area} fill="rgb(77 116 234 / 0.15)" />
          <path d={line} fill="none" stroke="rgb(77 116 234)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
        </svg>
      </figure>

      <figure className="card">
        <figcaption className="mb-2 flex items-baseline justify-between">
          <span className="text-xs font-medium text-ink/70">每日口碑指數</span>
          <span className="font-mono text-[11px] text-ink/70">中性線=0 · 上正下負</span>
        </figcaption>
        {hasSent ? (
          <svg
            viewBox={`0 0 ${W} ${SENT_H}`}
            className="h-20 w-full"
            preserveAspectRatio="none"
            role="img"
            aria-label="每日口碑指數趨勢"
          >
            {/* 中性基準線：ink 淺階（白卡上可見；原本的白色是暗色主題殘留、白底隱形）。 */}
            <line
              x1={PAD}
              y1={SENT_H / 2}
              x2={W - PAD}
              y2={SENT_H / 2}
              stroke="rgb(27 37 54 / 0.15)"
              strokeWidth="1"
              strokeDasharray="3 3"
              vectorEffect="non-scaling-stroke"
            />
            {/* 口碑線同走寶藍 accent（取代暗色主題殘留的 cyan）。 */}
            <path
              d={sentLine}
              fill="none"
              stroke="rgb(77 116 234)"
              strokeWidth="1.5"
              strokeLinejoin="round"
              vectorEffect="non-scaling-stroke"
            />
          </svg>
        ) : (
          <div className="flex h-20 items-center justify-center text-xs text-ink/70">
            這段期間尚無情緒資料。
          </div>
        )}
      </figure>

      <div className="flex justify-between px-1 font-mono text-[11px] text-ink/35">
        <span>{first}</span>
        <span>{last}</span>
      </div>
    </div>
  );
}
