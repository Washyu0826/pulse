import { FeedCard } from "@/components/feed-card";
import { SectionStatus } from "@/components/section-status";
import { THEME_META, THEME_ORDER } from "@/components/theme-meta";
import { getFeed } from "@/lib/api";
import type { FeedFilters } from "@/lib/types";

/**
 * 每日實用情報三主題分區（定位 C 門面，自帶 fetch，Suspense 內串流）。
 * 依 filters（模型/情緒/來源/時間）收斂；模型/情緒/來源是篩選維度，主題是主軸。
 */
export async function ThemeFeed({ filters }: { filters: FeedFilters }) {
  const feed = await getFeed(filters, 4);
  if (!feed.ok) {
    return <SectionStatus kind="error">無法載入情報，請確認 API 是否啟動</SectionStatus>;
  }

  const hasAny = THEME_ORDER.some((t) => (feed.data[t]?.length ?? 0) > 0);
  if (!hasAny) {
    return (
      <SectionStatus kind="empty">
        這個條件下目前沒有實用情報 —— 試試放寬時間、或把篩選改回「全部」。
      </SectionStatus>
    );
  }

  return (
    <div className="space-y-10">
      {THEME_ORDER.map((label) => {
        const posts = feed.data[label] ?? [];
        const meta = THEME_META[label];
        return (
          <section key={label}>
            <div className="mb-3.5 flex items-center gap-2.5">
              <span
                className={`flex h-7 w-7 items-center justify-center rounded-md ring-1 ${meta.bg} ${meta.text} ${meta.ring}`}
              >
                <meta.Icon className="h-4 w-4" />
              </span>
              <h3 className="text-base font-semibold text-white">{label}</h3>
              <span className="hidden text-[13px] text-white/40 sm:inline">{meta.blurb}</span>
              <span className="ml-auto font-mono text-xs text-white/35">{posts.length}</span>
            </div>
            {posts.length === 0 ? (
              <p className="rounded-lg border border-dashed border-border/50 px-4 py-5 text-center text-[13px] text-white/35">
                這個條件下這類沒有新內容。
              </p>
            ) : (
              <div className="grid gap-3 md:grid-cols-2">
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
