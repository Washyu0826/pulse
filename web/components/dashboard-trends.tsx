import { SentimentTrendChart } from "@/components/charts/sentiment-trend-chart";
import { ThemeTrendChart } from "@/components/charts/theme-trend-chart";
import { Section } from "@/components/section";
import { SectionStatus } from "@/components/section-status";
import { friendlyError, getDashboardTrends } from "@/lib/api";

/**
 * 主題趨勢 + 情緒走勢（自帶 fetch；Suspense 邊界內串流）。
 *
 * 兩條時序共用同一個 /api/dashboard/trends 請求（一次抓、避免重打），但各自區塊獨立呈現
 * 錯誤 / 空狀態：端點尚未上線或失敗 → 用 SectionStatus 顯示在地化「暫時載入不了」，不拖垮整頁；
 * 真的沒資料才顯示「尚無」。日期序由各圖元件處理（純函式邊界已測）。
 */
export async function DashboardTrends({ days = 14 }: { days?: number }) {
  const res = await getDashboardTrends(days);

  return (
    <div className="grid gap-8 lg:grid-cols-2">
      <Section label="主題趨勢" description={`近 ${days} 天五大實用主題的每日討論分布（堆疊面積）。`}>
        {!res.ok ? (
          <SectionStatus kind="error">
            {friendlyError(res.error, "主題趨勢暫時載入不了，稍後再試。")}
          </SectionStatus>
        ) : (
          <ThemeTrendChart trend={res.data.theme_trend} />
        )}
      </Section>

      <Section label="情緒走勢" description={`近 ${days} 天社群情緒（正 / 中性 / 負）的每日佔比。`}>
        {!res.ok ? (
          <SectionStatus kind="error">
            {friendlyError(res.error, "情緒走勢暫時載入不了，稍後再試。")}
          </SectionStatus>
        ) : (
          <SentimentTrendChart trend={res.data.sentiment_trend} />
        )}
      </Section>
    </div>
  );
}
