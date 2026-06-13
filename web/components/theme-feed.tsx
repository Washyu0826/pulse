import Link from "next/link";

import { FeedCard } from "@/components/feed-card";
import { SectionStatus } from "@/components/section-status";
import { THEME_META, THEME_ORDER } from "@/components/theme-meta";
import { friendlyError, getFeed } from "@/lib/api";
import type { FeedFilters } from "@/lib/types";

/** 主題列表頁連結（把首頁當前篩選帶過去 —— 看全部後 filter 隨行）。 */
function themeHref(label: string, filters: FeedFilters): string {
  const q = new URLSearchParams();
  if (filters.model) q.set("model", filters.model);
  if (filters.sentiment) q.set("sentiment", filters.sentiment);
  if (filters.source) q.set("source", filters.source);
  if (filters.days) q.set("days", String(filters.days));
  const qs = q.toString();
  return `/theme/${encodeURIComponent(label)}${qs ? `?${qs}` : ""}`;
}

/**
 * 每日實用情報三主題分區（定位 C 門面，自帶 fetch，Suspense 內串流）。
 * 依 filters（模型/情緒/來源/時間）收斂；模型/情緒/來源是篩選維度，主題是主軸。
 */
export async function ThemeFeed({ filters }: { filters: FeedFilters }) {
  const feed = await getFeed(filters, 4);
  if (!feed.ok) {
    return <SectionStatus kind="error">{friendlyError(feed.error, "情報暫時載入不了，稍後再試。")}</SectionStatus>;
  }

  const hasAny = THEME_ORDER.some((t) => (feed.data[t]?.length ?? 0) > 0);
  if (!hasAny) {
    return (
      <SectionStatus kind="empty">
        這個條件下目前沒有實用情報 —— 試試放寬時間、或把篩選改回「全部」。
      </SectionStatus>
    );
  }

  // 五主題並排成多欄（kanban），填滿寬度、一頁看完；窄螢幕自動堆疊。
  return (
    <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {THEME_ORDER.map((label) => {
        const posts = feed.data[label] ?? [];
        const meta = THEME_META[label];
        return (
          <section key={label}>
            <div className="mb-4 flex items-center gap-2.5 border-b border-border pb-2.5">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-md ring-1 ${meta.bg} ${meta.text} ${meta.ring}`}
              >
                <meta.Icon className="h-4 w-4" />
              </span>
              <h3 className="font-semibold text-ink">{label}</h3>
              <span className="ml-auto font-mono text-xs text-ink/35">{posts.length}</span>
              <Link
                href={themeHref(label, filters)}
                className="shrink-0 text-[11px] text-accent-primary/80 transition-colors hover:text-accent-primary"
              >
                看全部 →
              </Link>
            </div>
            {posts.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border px-4 py-5 text-center text-[13px] text-ink/35">
                這類目前沒有新內容。
              </p>
            ) : (
              <div className="space-y-3">
                {posts.map((p) => (
                  <FeedCard key={p.id} post={p} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
