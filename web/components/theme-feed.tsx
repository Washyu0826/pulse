import { FeedCard } from "@/components/feed-card";
import { SectionStatus } from "@/components/section-status";
import { getFeed } from "@/lib/api";
import type { FeedFilters } from "@/lib/types";

// 三大實用主題的呈現順序與外觀（新工具量最大擺第一）。
export const THEME_ORDER = ["新工具", "使用方法", "邊界"] as const;
const THEME_META: Record<string, { icon: string; blurb: string }> = {
  新工具: { icon: "🆕", blurb: "新發表的 AI 工具、模型、產品" },
  使用方法: { icon: "🛠️", blurb: "提示技巧、教學、工作流、use case" },
  邊界: { icon: "🚧", blurb: "限制、風險、要注意的坑" },
};

/**
 * 每日實用情報三主題分區（定位 C 門面，自帶 fetch，Suspense 內串流）。
 * 依 filters（模型/情緒/來源/時間）收斂；模型/情緒/來源是篩選維度，主題是主軸。
 */
export async function ThemeFeed({ filters }: { filters: FeedFilters }) {
  const feed = await getFeed(filters, 6);
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
    <div className="space-y-8">
      {THEME_ORDER.map((label) => {
        const posts = feed.data[label] ?? [];
        const meta = THEME_META[label];
        return (
          <section key={label}>
            <div className="mb-3 flex items-baseline gap-2">
              <h3 className="text-base font-semibold text-white">
                <span aria-hidden className="mr-1">
                  {meta.icon}
                </span>
                {label}
              </h3>
              <span className="text-[13px] text-white/40">{meta.blurb}</span>
            </div>
            {posts.length === 0 ? (
              <p className="text-[13px] text-white/35">這個條件下這類沒有新內容。</p>
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
