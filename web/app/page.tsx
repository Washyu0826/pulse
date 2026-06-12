/**
 * Pulse 首頁（定位 C）—— 左側「依模型瀏覽」側欄 + 右側「每日實用情報」主區。
 * 主區五主題分區（新工具/模型動態/使用方法/風險限制/倫理法規），模型/情緒/來源/時間為篩選維度。Hero 橫跨上方。
 *
 * 篩選狀態走 URL searchParams（?model=&sentiment=&source=&days=）→ 可分享、可後退、無自帶狀態。
 */
import { Suspense } from "react";

import { FeedFilter } from "@/components/feed-filter";
import { FeedSummary } from "@/components/feed-summary";
import { HeroIntro } from "@/components/hero-intro";
import { ModelRail } from "@/components/model-rail";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { ThemeFeed } from "@/components/theme-feed";
import { TodayEvents } from "@/components/today-events";
import { TrendingPanel } from "@/components/trending-panel";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";
import type { FeedFilters, Sentiment } from "@/lib/types";

const SENTIMENTS: Sentiment[] = ["positive", "neutral", "negative"];

export default function HomePage({
  searchParams,
}: {
  searchParams: { model?: string; sentiment?: string; source?: string; days?: string };
}) {
  const days = Number(searchParams.days) || 1; // 預設只看今日（滾動視窗）
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
      <main className="w-full px-6 py-12 lg:px-10 xl:px-16">
        <div className="animate-fade-up">
          <HeroIntro />
        </div>

        <div className="animate-fade-up mt-12 grid gap-10 lg:grid-cols-[190px_1fr] xl:grid-cols-[190px_1fr_230px] [animation-delay:120ms]">
          {/* 左側欄：依模型瀏覽（sticky） */}
          <aside className="h-fit lg:sticky lg:top-20">
            <Suspense fallback={<Skeleton className="h-48 w-full rounded-lg" />}>
              <ModelRail />
            </Suspense>
          </aside>

          {/* 中間主區：每日實用情報。窄螢幕單欄時排最前（05 #9：別讓模型側欄擋在情報前），lg 起恢復文件序。 */}
          <div className="order-first min-w-0 lg:order-none">
            <FeedFilter />
            <Suspense key={`sum:${feedKey}`} fallback={<Skeleton className="h-14 w-full rounded-xl" />}>
              <FeedSummary filters={filters} />
            </Suspense>

            {/* 今日事件：把相關貼文聚成事件 + 忠實摘要（含行內出處） */}
            <div className="mt-8">
              <Section
                label="今日事件"
                description="把今天多篇相關討論聚成事件，附忠實摘要與行內出處引用。"
              >
                <Suspense fallback={<CardGridSkeleton count={2} cols={2} />}>
                  <TodayEvents />
                </Suspense>
              </Section>
            </div>

            <div className="mt-10">
              <Suspense key={feedKey} fallback={<CardGridSkeleton count={6} cols={3} />}>
                <ThemeFeed filters={filters} />
              </Suspense>
            </div>
          </div>

          {/* 右側欄：本週熱詞（sticky；窄螢幕移到下方） */}
          <aside className="h-fit lg:col-span-2 lg:sticky lg:top-20 xl:col-span-1">
            <Suspense fallback={<Skeleton className="h-64 w-full rounded-lg" />}>
              <TrendingPanel />
            </Suspense>
          </aside>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}
