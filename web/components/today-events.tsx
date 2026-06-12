import { Fragment } from "react";
import { Layers } from "lucide-react";

import { SectionStatus } from "@/components/section-status";
import { themeMeta } from "@/components/theme-meta";
import { Badge } from "@/components/ui/badge";
import { getTodayEvents } from "@/lib/api";
import type { EventCitation, EventSummary } from "@/lib/types";

/**
 * 把摘要文字中的行內引用標記 [1][2] 切成可點的上標。
 * 找不到對應 citation 的標記就保留純文字（不假裝有連結），避免後端編號與清單對不齊時出錯。
 */
function renderSummary(summary: string, citations: EventCitation[]) {
  const byN = new Map(citations.map((c) => [c.n, c]));
  // 以 [數字] 為分隔，保留分隔符（捕獲群組）。
  const parts = summary.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (!m) return <Fragment key={i}>{part}</Fragment>;
    const n = Number(m[1]);
    const cite = byN.get(n);
    if (cite?.url) {
      return (
        <a
          key={i}
          href={cite.url}
          target="_blank"
          rel="noopener noreferrer"
          className="mx-0.5 align-super font-mono text-[10px] text-accent-primary hover:underline"
          aria-label={`出處 ${n}`}
        >
          [{n}]
        </a>
      );
    }
    return (
      <sup key={i} className="mx-0.5 font-mono text-[10px] text-ink/70">
        [{n}]
      </sup>
    );
  });
}

/** 單則今日事件卡：標題 + 主題徽章 + 成員貼文數 + 帶行內出處的忠實摘要 + 出處清單。 */
function EventSummaryCard({ ev }: { ev: EventSummary }) {
  const meta = themeMeta(ev.theme);
  return (
    <article className="card">
      <div className="flex items-center gap-2">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-md ring-1 ${meta.bg} ${meta.text} ${meta.ring}`}
        >
          <meta.Icon className="h-3.5 w-3.5" />
        </span>
        <Badge variant="neutral">{ev.theme}</Badge>
        <span
          title="此事件涵蓋的相關貼文數"
          className="ml-auto flex items-center gap-1 font-mono text-[11px] text-ink/45"
        >
          <Layers aria-hidden className="h-3 w-3" />
          {ev.memberCount} 篇
        </span>
      </div>
      <h3 className="mt-2.5 text-sm font-semibold leading-snug text-ink">{ev.title}</h3>
      <p className="mt-1.5 text-[13px] leading-relaxed text-ink/65">
        {renderSummary(ev.summary, ev.citations)}
      </p>
      {ev.citations.length > 0 && (
        <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-border/60 pt-2.5">
          <span className="font-mono text-[10px] uppercase tracking-wider text-ink/35">出處</span>
          {ev.citations.map((c) =>
            c.url ? (
              <a
                key={c.n}
                href={c.url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-mono text-[11px] text-accent-primary hover:underline"
              >
                [{c.n}]
              </a>
            ) : (
              <span key={c.n} className="font-mono text-[11px] text-ink/70">
                [{c.n}]
              </span>
            ),
          )}
        </div>
      )}
    </article>
  );
}

/**
 * 今日事件區（自帶 fetch；Suspense 邊界內串流）。
 * 把多篇相關貼文聚成事件並做忠實摘要 + 行內出處引用（產品差異化核心，非 RAG）。
 * 後端端點未上線 / 抓不到資料 → 退回「尚無今日事件」空狀態，不讓整頁掛掉。
 */
export async function TodayEvents() {
  const events = await getTodayEvents();
  if (!events.ok) {
    return <SectionStatus kind="empty">尚無今日事件 —— 等今天的貼文累積到可聚合的事件後會出現在這裡。</SectionStatus>;
  }
  if (events.data.length === 0) {
    return <SectionStatus kind="empty">尚無今日事件 —— 今天還沒有可聚合成事件的討論。</SectionStatus>;
  }
  return (
    <div className="grid gap-3 md:grid-cols-2">
      {events.data.map((ev) => (
        <EventSummaryCard key={ev.id} ev={ev} />
      ))}
    </div>
  );
}
