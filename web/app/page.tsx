/**
 * Pulse 首頁（定位 C）—— 以「每日實用情報」為門面：三主題分區（新工具/使用方法/邊界），
 * 模型/情緒/來源/時間為篩選維度。事件動態與模型看板降為次要區塊置於下方。
 *
 * 每區塊各自 async fetch、包在獨立 Suspense → header 立刻顯示、各區塊獨立串流。
 * 篩選狀態走 URL searchParams（?model=&sentiment=&source=&days=）→ 可分享、可後退、無自帶狀態。
 */
import { Suspense } from "react";

import { EventsFeed } from "@/components/events-feed";
import { EventsFilter } from "@/components/events-filter";
import { FeedFilter } from "@/components/feed-filter";
import { FeedSummary } from "@/components/feed-summary";
import { HeroIntro } from "@/components/hero-intro";
import { ModelBoard } from "@/components/model-board";
import { ReleasesFeed } from "@/components/releases-feed";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { ThemeFeed } from "@/components/theme-feed";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";
import type { EventType, FeedFilters, Sentiment } from "@/lib/types";

const EVENT_TYPES: EventType[] = ["discussion_spike", "launch", "sentiment_flip"];
const SENTIMENTS: Sentiment[] = ["positive", "neutral", "negative"];

export default function HomePage({
  searchParams,
}: {
  searchParams: { model?: string; sentiment?: string; source?: string; days?: string };
}) {
  // 實用情報篩選（門面）。
  const days = Number(searchParams.days) || 30;
  const filters: FeedFilters = {
    model: searchParams.model || undefined,
    sentiment: SENTIMENTS.includes(searchParams.sentiment as Sentiment)
      ? (searchParams.sentiment as Sentiment)
      : undefined,
    source: searchParams.source || undefined,
    days,
  };
  // 篩選改變 → 給 Suspense 一個隨 filters 變的 key，重新觸發骨架。
  const feedKey = `${filters.model ?? "all"}:${filters.sentiment ?? "all"}:${filters.source ?? "all"}:${days}`;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-5xl space-y-12 px-6 py-10">
        <HeroIntro />

        <Section
          label="每日實用情報"
          description="社群在討論的「新工具 / 怎麼用 / 要注意什麼」，過濾雜訊、可依模型與情緒篩選。"
        >
          <FeedFilter />
          <Suspense key={`sum:${feedKey}`} fallback={<Skeleton className="h-14 w-full rounded-lg" />}>
            <FeedSummary filters={filters} />
          </Suspense>
          <div className="mt-6">
            <Suspense key={feedKey} fallback={<CardGridSkeleton count={6} cols={2} />}>
              <ThemeFeed filters={filters} />
            </Suspense>
          </div>
        </Section>

        <Section
          label="事件動態"
          description="自動偵測：討論突增 / 新版發布 / 口碑翻轉。"
        >
          <EventsFilter />
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <EventsFeed />
          </Suspense>
        </Section>

        <Section label="最新發布" description="HuggingFace / GitHub 各模型最新版本釋出。">
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <ReleasesFeed />
          </Suspense>
        </Section>

        <Section label="模型即時看板" description="六大模型熱度與口碑，點卡片看詳情。">
          <Suspense fallback={<CardGridSkeleton count={6} cols={6} compact />}>
            <ModelBoard />
          </Suspense>
        </Section>
      </main>
      <SiteFooter />
    </>
  );
}
