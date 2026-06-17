/**
 * 產品洞察 dashboard `/dashboard` —— 單頁總覽，給使用者一眼掌握「今天 AI 圈在發生什麼」。
 *
 * 組裝既有元件，沿用設計系統與錯誤/載入/空狀態慣例（friendlyError / SectionStatus / Suspense skeleton）。
 * 全 Server Component + ISR（各 fetch wrapper next.revalidate=60）。每個區塊獨立 Suspense 邊界，
 * 單一區塊失敗（含後端時序端點尚未上線）不拖垮整頁。
 *
 * 區塊：今日事件（hero，NLP 核心）→ 主題/情緒趨勢 → 熱詞 + 模型動態。
 * 響應式：桌機多欄 grid、行動單欄且主內容（今日事件）排最前。
 */
import { Suspense } from "react";
import type { Metadata } from "next";

import { DashboardTrends } from "@/components/dashboard-trends";
import { FeedSummary } from "@/components/feed-summary";
import { ModelRail } from "@/components/model-rail";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { StorylineTimeline } from "@/components/storyline-timeline";
import { TodayEvents } from "@/components/today-events";
import { TrendingPanel } from "@/components/trending-panel";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";
import type { FeedFilters } from "@/lib/types";

export const metadata: Metadata = {
  title: "產品洞察",
  description:
    "一頁掌握今天的 AI 情報：忠實事件摘要、主題與情緒趨勢、熱詞與六大模型動態。",
  alternates: { canonical: "/dashboard" },
};

const TREND_DAYS = 14;

export default function DashboardPage() {
  // 今日分布固定看最近一天（與首頁預設一致的滾動視窗）。
  const todayFilters: FeedFilters = { days: 1 };

  return (
    <>
      <SiteHeader />
      <main className="w-full px-6 py-12 lg:px-10 xl:px-16">
        <div className="animate-fade-up">
          <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">產品洞察</h1>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-ink/55">
            一頁掌握今天的 AI 圈：把多篇相關討論聚成
            <span className="text-ink/85">忠實事件摘要</span>，再看
            <span className="text-ink/85">主題與情緒趨勢</span>、熱詞與六大模型動態。
          </p>
        </div>

        {/* 今日事件（hero，產品 NLP 核心）—— 行動裝置自然排最前。 */}
        <section className="animate-fade-up mt-10 [animation-delay:80ms]">
          <Section
            label="今日事件"
            description="把今天多篇相關討論聚成事件，附忠實摘要與行內出處引用 —— 這是 Pulse 的核心。"
          >
            <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
              <TodayEvents />
            </Suspense>
          </Section>

          {/* 今日各主題分布（輕量摘要列；非關鍵，失敗安靜隱藏）。 */}
          <div className="mt-6">
            <Suspense fallback={<Skeleton className="h-14 w-full rounded-xl" />}>
              <FeedSummary filters={todayFilters} />
            </Suspense>
          </div>
        </section>

        {/* 議題時間軸（跨日議題鏈的聲量走勢 + 升溫/退燒）—— NLP 進階：事件的時間維度。 */}
        <div className="animate-fade-up mt-12 [animation-delay:120ms]">
          <Section
            label="議題時間軸"
            description="把跨日延續的相關討論串成議題鏈，看每個議題的聲量走勢與升溫 / 高峰 / 退燒。"
          >
            <Suspense fallback={<CardGridSkeleton count={4} cols={2} />}>
              <StorylineTimeline limit={6} />
            </Suspense>
          </Section>
        </div>

        {/* 主題趨勢 + 情緒走勢（並排，桌機雙欄）。 */}
        <div className="animate-fade-up mt-12 [animation-delay:160ms]">
          <Suspense
            fallback={
              <div className="grid gap-8 lg:grid-cols-2">
                <Skeleton className="h-72 w-full rounded-xl" />
                <Skeleton className="h-72 w-full rounded-xl" />
              </div>
            }
          >
            <DashboardTrends days={TREND_DAYS} />
          </Suspense>
        </div>

        {/* 熱詞 + 模型動態（桌機並排）。 */}
        <div className="animate-fade-up mt-12 grid gap-8 lg:grid-cols-[1fr_280px] [animation-delay:240ms]">
          <Section label="模型動態" description="六大模型近期討論熱度，點進看詳細趨勢與事件。">
            <Suspense fallback={<Skeleton className="h-64 w-full rounded-lg" />}>
              <ModelRail />
            </Suspense>
          </Section>

          <aside className="h-fit lg:sticky lg:top-20">
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
