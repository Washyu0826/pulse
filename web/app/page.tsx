/**
 * Pulse 首頁 —— 開場說明 + 近期動態摘要 + 事件流 + 最新發布 + 6 模型看板。
 *
 * 每個區塊各自 async fetch、包在獨立 Suspense 內 → header 立刻顯示、各區塊獨立串流。
 * 任一區塊失敗只影響自己（lib/api 的 wrapper 不 throw）。
 */
import { Suspense } from "react";

import { EventsFeed } from "@/components/events-feed";
import { HeroIntro } from "@/components/hero-intro";
import { ModelBoard } from "@/components/model-board";
import { ReleasesFeed } from "@/components/releases-feed";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { TodaySummary } from "@/components/today-summary";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-5xl space-y-10 px-6 py-10">
        <HeroIntro />

        <Suspense fallback={<Skeleton className="h-20 w-full rounded-lg" />}>
          <TodaySummary />
        </Suspense>

        <Section
          label="事件動態"
          description="系統自動偵測的「討論突增」與「新版發布」，依重要性排序。"
        >
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <EventsFeed />
          </Suspense>
        </Section>

        <Section
          label="最新發布"
          description="HuggingFace / GitHub 上各模型最新的版本釋出，可點進原始頁面。"
        >
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <ReleasesFeed />
          </Suspense>
        </Section>

        <Section
          label="模型即時看板"
          description="六大模型的討論熱度：累計貼文數 · 近 7 天增量 · 是否異常升溫。"
        >
          <Suspense fallback={<CardGridSkeleton count={6} cols={6} compact />}>
            <ModelBoard />
          </Suspense>
        </Section>
      </main>
      <SiteFooter />
    </>
  );
}
