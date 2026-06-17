import { Flame, Snowflake, TrendingUp } from "lucide-react";

import { SectionStatus } from "@/components/section-status";
import { themeMeta } from "@/components/theme-meta";
import { Badge } from "@/components/ui/badge";
import { friendlyError, getStorylines } from "@/lib/api";
import { buildSparkline } from "@/lib/trend-path";
import type { Storyline, StorylineState, TimelinePoint } from "@/lib/types";

/**
 * 議題時間軸（自帶 fetch；Suspense 邊界內串流）。
 *
 * 把跨日相關事件串成「議題鏈」，呈現每條議題的標題、狀態徽章（升溫/高峰/退燒/持平）、
 * 跨日聲量走勢（純 SVG sparkline，與 charts/* 同調、零依賴 SSR 友善），各日一句重點與出處連結。
 *
 * 資料由 /api/storylines（build_storylines.py 每日產製）提供；端點尚未產出或失敗 → SectionStatus
 * 顯示在地化「暫時載入不了」，真的沒議題鏈才顯示「尚無」。皆不拖垮整頁。
 */

// 狀態 → 徽章樣式 + icon（沿用設計系統的 sentiment token，維持克制配色）。
const STATE_META: Record<
  StorylineState,
  { variant: "accent" | "warn" | "neutral"; Icon: typeof Flame; label: string }
> = {
  升溫: { variant: "accent", Icon: TrendingUp, label: "升溫" },
  高峰: { variant: "warn", Icon: Flame, label: "高峰" },
  退燒: { variant: "neutral", Icon: Snowflake, label: "退燒" },
  持平: { variant: "neutral", Icon: TrendingUp, label: "持平" },
};

const SPARK_W = 240;
const SPARK_H = 36;
const SPARK_PAD = 3;

/** 跨日聲量 sparkline（折線 + 點），純 SVG。單點時退化為一個點。 */
function VolumeSparkline({ timeline }: { timeline: TimelinePoint[] }) {
  const vols = timeline.map((t) => t.volume);
  const n = vols.length;
  // 座標數學集中到 trend-path 的 buildSparkline（與面積/折線圖共用、有測試）。
  const { line, points } = buildSparkline(vols, {
    width: SPARK_W,
    height: SPARK_H,
    pad: SPARK_PAD,
  });
  const last = n - 1;

  return (
    <svg
      viewBox={`0 0 ${SPARK_W} ${SPARK_H}`}
      className="h-9 w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label={`跨 ${n} 天聲量走勢`}
    >
      {n > 1 && (
        <polyline
          points={line}
          fill="none"
          stroke="rgb(77 116 234 / 0.7)"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          vectorEffect="non-scaling-stroke"
        />
      )}
      {points.map((p, i) => (
        <circle
          key={i}
          cx={p.x}
          cy={p.y}
          r={i === last ? 2.5 : 1.5}
          fill={i === last ? "rgb(77 116 234)" : "rgb(77 116 234 / 0.5)"}
        />
      ))}
    </svg>
  );
}

/** 單條議題卡：主題 + 狀態徽章 + 標題 + 聲量 sparkline + 各日一句重點（含出處連結）。 */
function StorylineCard({ story }: { story: Storyline }) {
  const meta = themeMeta(story.theme);
  const state = STATE_META[story.state] ?? STATE_META.升溫;
  // 出處：以時間軸日期對齊 citations（n 為 1-based）。
  const citeByN = new Map(story.citations.map((c) => [c.n, c]));

  return (
    <article className="card">
      <div className="flex items-center gap-2">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-md ring-1 ${meta.bg} ${meta.text} ${meta.ring}`}
        >
          <meta.Icon className="h-3.5 w-3.5" />
        </span>
        <Badge variant="neutral">{story.theme}</Badge>
        <Badge variant={state.variant} className="gap-1">
          <state.Icon aria-hidden className="h-3 w-3" />
          {state.label}
        </Badge>
        <span className="ml-auto font-mono text-[11px] text-ink/45" title="此議題涵蓋的天數">
          跨 {story.spanDays} 天
        </span>
      </div>

      <h3 className="mt-2.5 text-sm font-semibold leading-snug text-ink">{story.title}</h3>

      <div className="mt-3">
        <VolumeSparkline timeline={story.timeline} />
      </div>

      {/* 各日一句重點時間軸（左側日期 + 一句摘要 + 出處）。 */}
      <ol className="mt-3 space-y-1.5 border-t border-border/60 pt-2.5">
        {story.timeline.map((t, i) => {
          const cite = citeByN.get(i + 1);
          return (
            <li key={t.date} className="flex items-baseline gap-2 text-[12px] leading-relaxed">
              <span className="shrink-0 font-mono text-[10px] tabular-nums text-ink/35">
                {t.date.slice(5)}
              </span>
              <span className="text-ink/70">{t.summary || "（當日無重點）"}</span>
              {cite?.url && (
                <a
                  href={cite.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 font-mono text-[10px] text-accent-primary hover:underline"
                  aria-label={`第 ${i + 1} 天出處`}
                >
                  [{i + 1}]
                </a>
              )}
            </li>
          );
        })}
      </ol>
    </article>
  );
}

export async function StorylineTimeline({ limit = 6 }: { limit?: number }) {
  const res = await getStorylines(limit);
  if (!res.ok) {
    return (
      <SectionStatus kind="error">
        {friendlyError(res.error, "議題時間軸暫時載入不了，稍後再試。")}
      </SectionStatus>
    );
  }
  if (res.data.length === 0) {
    return (
      <SectionStatus kind="empty">
        尚無議題時間軸 —— 近期還沒有跨日延續、可串成議題的討論。
      </SectionStatus>
    );
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {res.data.map((story) => (
        <StorylineCard key={story.id} story={story} />
      ))}
    </div>
  );
}
