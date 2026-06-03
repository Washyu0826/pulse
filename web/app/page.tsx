/**
 * Pulse 首頁（定位 C）—— 聚焦「每日實用情報」：三主題分區（新工具/使用方法/邊界），
 * 模型/情緒/來源/時間為篩選維度。底部保留精簡「依模型瀏覽」作為模型頁入口。
 *
 * 刻意精簡：事件流 / 最新發布等次要區塊不放首頁，避免資訊過載（定位 C）。
 * 篩選狀態走 URL searchParams（?model=&sentiment=&source=&days=）→ 可分享、可後退、無自帶狀態。
 */
import { Suspense } from "react";

import { FeedFilter } from "@/components/feed-filter";
import { FeedSummary } from "@/components/feed-summary";
import { HeroIntro } from "@/components/hero-intro";
import { ModelBoard } from "@/components/model-board";
import { Section } from "@/components/section";
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
      <main className="mx-auto max-w-4xl space-y-20 px-6 py-12">
        <HeroIntro />

        <section>
          <FeedFilter />
          <Suspense key={`sum:${feedKey}`} fallback={<Skeleton className="h-14 w-full rounded-xl" />}>
            <FeedSummary filters={filters} />
          </Suspense>
          <div className="mt-8">
            <Suspense key={feedKey} fallback={<CardGridSkeleton count={4} cols={2} />}>
              <ThemeFeed filters={filters} />
            </Suspense>
          </div>
        </section>

        <Section label="依模型瀏覽" description="想單看某個模型？點卡片進詳情頁。">
          <Suspense fallback={<CardGridSkeleton count={6} cols={6} compact />}>
            <ModelBoard />
          </Suspense>
        </Section>
      </main>
      <SiteFooter />
    </>
  );
}
