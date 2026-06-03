/**
 * Pulse 首頁（定位 C）—— 左側「依模型瀏覽」側欄 + 右側「每日實用情報」主區。
 * 主區三主題分區（新工具/使用方法/邊界），模型/情緒/來源/時間為篩選維度。Hero 橫跨上方。
 *
 * 篩選狀態走 URL searchParams（?model=&sentiment=&source=&days=）→ 可分享、可後退、無自帶狀態。
 */
import { Suspense } from "react";

import { FeedFilter } from "@/components/feed-filter";
import { FeedSummary } from "@/components/feed-summary";
import { HeroIntro } from "@/components/hero-intro";
import { ModelRail } from "@/components/model-rail";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { ThemeFeed } from "@/components/theme-feed";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";
import type { FeedFilters, Sentiment } from "@/lib/types";

const SENTIMENTS: Sentiment[] = ["positive", "neutral", "negative"];

export default function HomePage({
  searchParams,
}: {
  searchParams: { model?: string; sentiment?: string; source?: string; days?: string };
}) {
  const days = Number(searchParams.days) || 30;
  const filters: FeedFilters = {
    model: searchParams.model || undefined,
    sentiment: SENTIMENTS.includes(searchParams.sentiment as Sentiment)
      ? (searchParams.sentiment as Sentiment)
      : undefined,
    source: searchParams.source || undefined,
    days,
  };
  const feedKey = `${filters.model ?? "all"}:${filters.sentiment ?? "all"}:${filters.source ?? "all"}:${days}`;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-6 py-12">
        <HeroIntro />

        <div className="mt-12 grid gap-8 lg:grid-cols-[180px_1fr]">
          {/* 左側欄：依模型瀏覽（sticky） */}
          <aside className="h-fit lg:sticky lg:top-20">
            <Suspense fallback={<Skeleton className="h-48 w-full rounded-lg" />}>
              <ModelRail />
            </Suspense>
          </aside>

          {/* 右主區：每日實用情報 */}
          <div>
            <FeedFilter />
            <Suspense key={`sum:${feedKey}`} fallback={<Skeleton className="h-14 w-full rounded-xl" />}>
              <FeedSummary filters={filters} />
            </Suspense>
            <div className="mt-8">
              <Suspense key={feedKey} fallback={<CardGridSkeleton count={6} cols={3} />}>
                <ThemeFeed filters={filters} />
              </Suspense>
            </div>
          </div>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
