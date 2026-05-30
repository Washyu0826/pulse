import { Activity, Rocket, TrendingDown, TrendingUp } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/time";
import type { DetectedEvent } from "@/lib/types";

/** severity(0-10) → 白話文字標籤（市面慣例：用詞比數字好掃）。 */
function severityWord(score: number): string {
  if (score >= 8) return "爆量";
  if (score >= 5) return "熱議";
  return "升溫";
}

function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

function str(v: unknown): string | null {
  return typeof v === "string" && v.trim() ? v : null;
}

function SpikeCard({ ev }: { ev: DetectedEvent }) {
  const count = num(ev.extra?.count);
  const median = num(ev.extra?.median);
  const cause = str(ev.extra?.top_post);
  // median 可能為 0（平日幾乎無討論）→ 不能除，改用「突然」框架；否則顯示倍數。
  const multiple = count != null && median != null && median > 0
    ? Math.round((count / median) * 10) / 10
    : null;
  return (
    <div className="card">
      <div className="flex items-center gap-2">
        <Activity aria-hidden className="h-3.5 w-3.5 shrink-0 text-sentiment-neutral" />
        <Badge variant="neutral">討論突增</Badge>
        {ev.model && <Badge variant="accent">{ev.model}</Badge>}
        {ev.score != null && (
          <span title="比平常高多少；越高代表越罕見（與近期每日平均相比）">
            <Badge variant="warn">{severityWord(ev.score)}</Badge>
          </span>
        )}
        <time className="ml-auto shrink-0 font-mono text-xs text-white/45">
          {relativeTime(ev.occurred_at)}
        </time>
      </div>
      <h3 className="mt-2.5 text-sm font-medium leading-snug text-white">
        {ev.model ?? "某模型"} 討論量{" "}
        {multiple ? (
          <>約為平常的 <span className="text-sentiment-neutral">{multiple}×</span></>
        ) : median === 0 ? (
          <>從幾乎無人討論 <span className="text-sentiment-neutral">突然爆量</span></>
        ) : (
          "明顯升高"
        )}
      </h3>
      {count != null && median != null && (
        <p className="mt-1 font-mono text-xs text-white/45">
          {count} 篇 · 平日約 {median} 篇/天
        </p>
      )}
      {cause && (
        <p className="mt-1 truncate text-[13px] text-white/60">
          主要討論：<span className="text-white/75">{cause}</span>
        </p>
      )}
    </div>
  );
}

function LaunchCard({ ev }: { ev: DetectedEvent }) {
  return (
    <div className="card">
      <div className="flex items-center gap-2">
        <Rocket aria-hidden className="h-3.5 w-3.5 shrink-0 text-accent-cyan" />
        <Badge variant="neutral">新發布</Badge>
        {ev.model && <Badge variant="accent">{ev.model}</Badge>}
        <time className="ml-auto shrink-0 font-mono text-xs text-white/45">
          {relativeTime(ev.occurred_at)}
        </time>
      </div>
      <h3 className="mt-2.5 text-sm font-medium leading-snug text-white">{ev.title}</h3>
      {ev.description && (
        <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-white/60">
          {ev.description}
        </p>
      )}
    </div>
  );
}

function FlipCard({ ev }: { ev: DetectedEvent }) {
  const toNeg = str(ev.extra?.direction) === "to_negative";
  const Icon = toNeg ? TrendingDown : TrendingUp;
  const color = toNeg ? "text-sentiment-negative" : "text-sentiment-positive";
  return (
    <div className="card">
      <div className="flex items-center gap-2">
        <Icon aria-hidden className={`h-3.5 w-3.5 shrink-0 ${color}`} />
        <Badge variant={toNeg ? "warn" : "neutral"}>口碑翻轉</Badge>
        {ev.model && <Badge variant="accent">{ev.model}</Badge>}
        <time className="ml-auto shrink-0 font-mono text-xs text-white/45">
          {relativeTime(ev.occurred_at)}
        </time>
      </div>
      <h3 className="mt-2.5 text-sm font-medium leading-snug text-white">{ev.title}</h3>
      {ev.description && (
        <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-white/60">
          {ev.description}
        </p>
      )}
    </div>
  );
}

/** 單筆偵測事件卡片（純展示，Server Component）。 */
export function EventCard({ ev }: { ev: DetectedEvent }) {
  if (ev.event_type === "discussion_spike") return <SpikeCard ev={ev} />;
  if (ev.event_type === "sentiment_flip") return <FlipCard ev={ev} />;
  return <LaunchCard ev={ev} />;
}
