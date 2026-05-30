/**
 * Pulse 首頁 —— 事件流 + 最新發布 + 6 模型看板。
 *
 * 每個區塊各自 async fetch，包在獨立 Suspense 內 → header 立刻顯示、各區塊獨立串流。
 * 任一區塊失敗只影響自己（lib/api 的 wrapper 不 throw）。
 */
import { Suspense } from "react";

import { EventsFeed } from "@/components/events-feed";
import { ModelBoard } from "@/components/model-board";
import { ReleasesFeed } from "@/components/releases-feed";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { CardGridSkeleton } from "@/components/ui/skeleton";

export default function HomePage() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-5xl space-y-12 px-6 py-10">
        <Section label="事件流 · 偵測到的突增與發布">
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <EventsFeed />
          </Suspense>
        </Section>

        <Section label="最新發布 · HuggingFace + GitHub">
          <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
            <ReleasesFeed />
          </Suspense>
        </Section>

        <Section label="模型即時看板">
          <Suspense fallback={<CardGridSkeleton count={6} cols={6} compact />}>
            <ModelBoard />
          </Suspense>
        </Section>
      </main>
      <SiteFooter />
    </>
  );
}
