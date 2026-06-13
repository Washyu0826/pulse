/**
 * 模型詳情頁 `/models/[slug]` —— 點看板卡片進來：
 * 彙總指標 + 趨勢圖（討論量 + 口碑）+ 近期事件 + 熱門討論 + 最新發布。
 *
 * 資料來自單一 API（/api/models/{slug}），整頁一次抓；失敗或查無 → 友善狀態 / 404。
 */
import { notFound } from "next/navigation";
import { ArrowUpRight } from "lucide-react";

import { BackLink } from "@/components/back-link";
import { TrendChart } from "@/components/charts/trend-chart";
import { EventCard } from "@/components/event-card";
import { ReleaseCard } from "@/components/release-card";
import { Section } from "@/components/section";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";
import { InfoHint } from "@/components/ui/info-hint";
import { friendlyError, getModelDetail, isNotFound } from "@/lib/api";
import { sentimentClass, sentimentWord } from "@/lib/sentiment";
import { relativeTime } from "@/lib/time";
import type { ModelDetail } from "@/lib/types";

export const dynamicParams = true;

function Metric({
  value,
  label,
  className,
  hint,
}: {
  value: string;
  label: string;
  className?: string;
  hint?: React.ReactNode;
}) {
  return (
    <div className="card">
      <div className="flex items-center gap-1 text-[11px] text-ink/45">
        {label}
        {hint && <InfoHint label={label}>{hint}</InfoHint>}
      </div>
      <div className={`mt-1 font-mono text-xl font-semibold tabular-nums ${className ?? "text-ink"}`}>
        {value}
      </div>
    </div>
  );
}

export default async function ModelDetailPage({ params }: { params: { slug: string } }) {
  const res = await getModelDetail(params.slug, 30);

  if (!res.ok) {
    // 404（查無模型）→ Next 的 not-found；其他錯誤 → 友善頁內提示（在地化原始錯誤代碼）。
    if (isNotFound(res.error)) notFound();
    return (
      <>
        <SiteHeader />
        <main className="mx-auto max-w-4xl px-6 py-10">
          <BackLink />
          <div className="card mt-6 text-center text-sm text-sentiment-negative">
            {friendlyError(res.error, "這個模型的詳情暫時載入不了，稍後再試。")}
          </div>
        </main>
        <SiteFooter />
      </>
    );
  }

  const m: ModelDetail = res.data;
  const sIdx = m.sentiment_index;

  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-4xl space-y-8 px-6 py-10">
        <div>
          <BackLink />
          <div className="mt-4 flex flex-wrap items-baseline gap-x-3 gap-y-1">
            <h1 className="text-2xl font-semibold tracking-tight text-ink">{m.name}</h1>
            <span className="text-sm text-ink/45">{m.company}</span>
            {m.role && <span className="text-sm text-ink/45">· {m.role}</span>}
          </div>
          <p className="mt-2 text-sm text-ink/70">
            這個模型在技術社群的討論熱度與口碑，過去 {m.trend_days} 天的走勢。
          </p>
        </div>

        {/* 彙總指標 */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Metric
            value={m.posts_total.toLocaleString()}
            label="累計討論"
            hint="至今所有來源中提到此模型的貼文總數。"
          />
          <Metric
            value={m.posts_recent > 0 ? `+${m.posts_recent}` : "0"}
            label="近 7 天新增"
            className={m.posts_recent > 0 ? "text-sentiment-positive" : "text-ink/70"}
            hint="過去 7 天新增的相關討論數。"
          />
          <Metric
            value={sIdx == null ? "—" : sIdx > 0 ? `+${sIdx}` : String(sIdx)}
            label={`口碑（${sentimentWord(sIdx)}）`}
            className={sentimentClass(sIdx)}
            hint="好評/負評淨值 −100~100（正=多數好評）。"
          />
          <Metric
            value={String(m.releases_total)}
            label="累計發布"
            hint="HuggingFace / GitHub 偵測到的版本釋出。"
          />
        </div>

        {/* 趨勢圖 */}
        <Section label="趨勢" description="上：每日討論量；下：每日口碑指數（中性線=0）。">
          <TrendChart trend={m.trend} />
        </Section>

        {/* 近期事件 */}
        <Section label="近期事件" description="系統針對此模型偵測到的討論突增 / 發布 / 口碑翻轉。">
          {m.events.length === 0 ? (
            <div className="card text-center text-sm text-ink/45">
              此模型近期沒有偵測到特別事件 —— 一切平穩。
            </div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {m.events.map((ev) => (
                <EventCard key={ev.id} ev={ev} />
              ))}
            </div>
          )}
        </Section>

        {/* 熱門討論 */}
        <Section label="熱門討論" description="社群中分數最高的相關討論（依來源分數排序）。">
          {m.top_discussions.length === 0 ? (
            <div className="card text-center text-sm text-ink/45">尚無相關討論。</div>
          ) : (
            <ul className="space-y-2">
              {m.top_discussions.map((d, i) => (
                <li key={i} className="card-interactive">
                  {d.url ? (
                    <a
                      href={d.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-start gap-2 text-sm text-ink/85 hover:text-ink"
                    >
                      <span className="flex-1">{d.title}</span>
                      <ArrowUpRight className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink/40" aria-hidden />
                    </a>
                  ) : (
                    <span className="text-sm text-ink/85">{d.title}</span>
                  )}
                  <div className="mt-1 font-mono text-[11px] text-ink/70">
                    {d.source} · {d.score} 分
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Section>

        {/* 最新發布 */}
        <Section label="最新發布" description="此模型最近的版本釋出（可點進原始頁面）。">
          {m.releases.length === 0 ? (
            <div className="card text-center text-sm text-ink/45">尚無發布紀錄。</div>
          ) : (
            <div className="grid gap-3 md:grid-cols-2">
              {m.releases.map((r) => (
                <ReleaseCard key={r.id} ev={r} />
              ))}
            </div>
          )}
        </Section>

        {m.latest_release_at && (
          <p className="font-mono text-[11px] text-ink/35">
            最近一次發布：{relativeTime(m.latest_release_at)}
          </p>
        )}
      </main>
      <SiteFooter />
    </>
  );
}
