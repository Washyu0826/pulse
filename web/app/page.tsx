/**
 * Pulse 首頁 —— 開場說明 + 怎麼用引導 + 近期動態摘要 + 事件流 + 最新發布 + 6 模型看板。
 *
 * 每個區塊各自 async fetch、包在獨立 Suspense 內 → header 立刻顯示、各區塊獨立串流。
 * 任一區塊失敗只影響自己（lib/api 的 wrapper 不 throw）。
 *
 * 事件流的篩選狀態走 URL searchParams（?type=&model=）→ 可分享、可後退、無自帶狀態。
 */
import { Suspense } from "react";

import { EventsFeed } from "@/components/events-feed";
import { EventsFilter } from "@/components/events-filter";
import { HeroIntro } from "@/components/hero-intro";
import { HowToUse } from "@/components/how-to-use";
import { ModelBoard } from "@/components/model-board";
import { ReleasesFeed } from "@/components/releases-feed";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { TodaySummary } from "@/components/today-summary";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";
import type { EventType } from "@/lib/types";

const EVENT_TYPES: EventType[] = ["discussion_spike", "launch", "sentiment_flip"];

export default function HomePage({
  searchParams,
}: {
  searchParams: { type?: string; model?: string };
}) {
  const rawType = searchParams.type;
  const eventType = EVENT_TYPES.includes(rawType as EventType) ? (rawType as EventType) : undefined;
  const model = searchParams.model || undefined;
  // 篩選會改變內容 → 給 Suspense 一個隨 params 變的 key，重新觸發 fallback 骨架。
  const feedKey = `${eventType ?? "all"}:${model ?? "all"}`;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-5xl space-y-10 px-6 py-10">
        <HeroIntro />

        <HowToUse />

        <Suspense fallback={<Skeleton className="h-20 w-full rounded-lg" />}>
          <TodaySummary />
        </Suspense>

        <Section
          label="事件動態"
          description="自動偵測：討論突增 / 新版發布 / 口碑翻轉。"
        >
          <EventsFilter />
          <Suspense key={feedKey} fallback={<CardGridSkeleton count={4} cols={2} />}>
            <EventsFeed eventType={eventType} model={model} />
          </Suspense>
        </Section>

        <Section
          label="最新發布"
          description="HuggingFace / GitHub 各模型最新版本釋出。"
        >
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <ReleasesFeed />
          </Suspense>
        </Section>

        <Section
          label="模型即時看板"
          description="六大模型熱度與口碑，點卡片看詳情。"
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
