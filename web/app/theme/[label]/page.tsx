/**
 * 主題列表頁 `/theme/[label]` —— 單一主題的完整情報列表（旅程 b「看全部」的落點）。
 *
 * 重用首頁的 FeedFilter / FeedCard；篩選狀態同樣走 URL searchParams（?model=&sentiment=&source=&days=）
 * → 可分享、可後退、與首頁互通（首頁「看全部 →」會把當前篩選帶過來）。
 * 後端 `/api/feed?theme=` 只收 5 個實用主題——「其他」（低信心暫存）與未知主題在前端兜底，不打後端。
 */
import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Suspense } from "react";

import { FeedCard } from "@/components/feed-card";
import { FeedFilter } from "@/components/feed-filter";
import { SectionStatus } from "@/components/section-status";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { OTHER_THEME, THEME_META, THEME_ORDER } from "@/components/theme-meta";
import { CardGridSkeleton } from "@/components/ui/skeleton";
import { getThemeFeed } from "@/lib/api";
import type { FeedFilters, Sentiment, ThemeLabel } from "@/lib/types";

const SENTIMENTS: Sentiment[] = ["positive", "neutral", "negative"];
// 後端 limit_per_theme 上限 50（feed router ge=1 le=50）。
const LIST_LIMIT = 50;

/** URL 片段 → 主題字串（中文 label 會被 percent-encode；解不開就原樣回傳兜底）。 */
function decodeLabel(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return raw;
  }
}

function isActionableTheme(label: string): label is ThemeLabel {
  return (THEME_ORDER as readonly string[]).includes(label);
}

export function generateMetadata({ params }: { params: { label: string } }): Metadata {
  const label = decodeLabel(params.label);
  if (!isActionableTheme(label)) return { title: "主題情報" };
  return {
    title: `${label}情報`,
    description: `「${label}」主題的完整 AI 實用情報列表 —— ${THEME_META[label].blurb}。`,
  };
}

export default function ThemePage({
  params,
  searchParams,
}: {
  params: { label: string };
  searchParams: { model?: string; sentiment?: string; source?: string; days?: string };
}) {
  const label = decodeLabel(params.label);
  const days = Number(searchParams.days) || 1; // 與首頁同預設（今日）
  const filters: FeedFilters = {
    model: searchParams.model || undefined,
    sentiment: SENTIMENTS.includes(searchParams.sentiment as Sentiment)
      ? (searchParams.sentiment as Sentiment)
      : undefined,
    source: searchParams.source || undefined,
    days,
  };
  const feedKey = `${label}:${filters.model ?? "all"}:${filters.sentiment ?? "all"}:${filters.source ?? "all"}:${days}`;

  // 未知主題（含低信心「其他」）：不打後端（會 422），給友善兜底＋可去的 5 個主題。
  if (!isActionableTheme(label)) {
    return (
      <>
        <SiteHeader />
        <main className="mx-auto max-w-4xl px-6 py-12">
          <BackHome />
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-ink">
            {label === OTHER_THEME ? "其他（低信心）" : "找不到這個主題"}
          </h1>
          <p className="mt-2 max-w-prose text-sm leading-relaxed text-ink/70">
            {label === OTHER_THEME
              ? "「其他」是分類信心不足的暫存區，不列入實用情報列表 —— 等模型更有把握，它們會出現在對的主題裡。"
              : "Pulse 的情報目前分成下面五個主題，挑一個看看："}
          </p>
          <div className="mt-6 flex flex-wrap gap-2">
            {THEME_ORDER.map((t) => {
              const meta = THEME_META[t];
              return (
                <Link
                  key={t}
                  href={`/theme/${encodeURIComponent(t)}`}
                  className="flex items-center gap-2 rounded-lg border border-border px-3.5 py-2 text-sm text-ink/75 transition-colors hover:border-accent-primary/40 hover:text-ink"
                >
                  <meta.Icon className="h-4 w-4 text-accent-primary" aria-hidden />
                  {t}
                </Link>
              );
            })}
          </div>
        </main>
        <SiteFooter />
      </>
    );
  }

  const meta = THEME_META[label];
  return (
    <>
      <SiteHeader />
      <main className="w-full px-6 py-12 lg:px-10 xl:px-16">
        <BackHome />
        <div className="mt-4 flex items-center gap-3">
          <span
            className={`flex h-9 w-9 items-center justify-center rounded-lg ring-1 ${meta.bg} ${meta.text} ${meta.ring}`}
          >
            <meta.Icon className="h-5 w-5" />
          </span>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{label}</h1>
        </div>
        <p className="mb-8 mt-2 text-sm text-ink/45">
          {meta.blurb} —— 這個主題的完整列表，可再用下方篩選收斂。
        </p>
        <FeedFilter />
        <div className="mt-6">
          <Suspense key={feedKey} fallback={<CardGridSkeleton count={6} cols={3} />}>
            <ThemePostList label={label} filters={filters} />
          </Suspense>
        </div>
      </main>
      <SiteFooter />
    </>
  );
}

/** 自帶 fetch 的列表本體（Suspense 內串流，與首頁 ThemeFeed 同模式）。 */
async function ThemePostList({ label, filters }: { label: ThemeLabel; filters: FeedFilters }) {
  const feed = await getThemeFeed(label, filters, LIST_LIMIT);
  if (!feed.ok) {
    return <SectionStatus kind="error">情報暫時載入不了，稍後再試。</SectionStatus>;
  }
  if (feed.data.length === 0) {
    return (
      <SectionStatus kind="empty">
        <span>
          這個條件下「{label}」目前沒有內容 ——{" "}
          <Link
            href={`/theme/${encodeURIComponent(label)}?days=7`}
            className="text-accent-primary hover:underline"
          >
            看看近 7 天 →
          </Link>
        </span>
      </SectionStatus>
    );
  }
  return (
    <>
      <p className="mb-4 font-mono text-xs text-ink/45">
        共 {feed.data.length} 則{feed.data.length >= LIST_LIMIT ? `（最多顯示 ${LIST_LIMIT} 則，可用篩選收斂）` : ""}
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {feed.data.map((p) => (
          <FeedCard key={p.id} post={p} />
        ))}
      </div>
    </>
  );
}

function BackHome() {
  return (
    <Link
      href="/"
      className="inline-flex items-center gap-1 text-xs text-ink/50 transition-colors hover:text-ink"
    >
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
      回今日情報
    </Link>
  );
}
