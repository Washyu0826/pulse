import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/time";
import type { FeedPost, Sentiment } from "@/lib/types";

/** 來源顯示名；Threads 標 🌏 凸顯中文在地（定位 C 差異化）。 */
const SOURCE_META: Record<string, { label: string; local?: boolean }> = {
  hackernews: { label: "HN" },
  devto: { label: "Dev.to" },
  lobsters: { label: "Lobsters" },
  threads: { label: "Threads", local: true },
  reddit: { label: "Reddit" },
  twitter: { label: "X" },
};

/** 情緒 → 圓點顏色 + 說明。null = 未分析（不假裝中性）。 */
const SENTIMENT_DOT: Record<Sentiment, { cls: string; word: string }> = {
  positive: { cls: "bg-sentiment-positive", word: "正面" },
  neutral: { cls: "bg-sentiment-neutral", word: "中性" },
  negative: { cls: "bg-sentiment-negative", word: "負面" },
};

function SentimentDot({ s }: { s: Sentiment | null }) {
  if (s === null) {
    return <span title="情緒未分析" className="h-2 w-2 shrink-0 rounded-full bg-white/20" />;
  }
  const d = SENTIMENT_DOT[s];
  return <span title={`情緒：${d.word}`} className={`h-2 w-2 shrink-0 rounded-full ${d.cls}`} />;
}

/** 單則實用情報卡片（純展示，Server Component）。 */
export function FeedCard({ post }: { post: FeedPost }) {
  const src = SOURCE_META[post.source] ?? { label: post.source };
  const body = (
    <div className="card h-full">
      <div className="flex items-center gap-1.5">
        <SentimentDot s={post.sentiment} />
        {post.models.map((m) => (
          <Badge key={m} variant="accent">
            {m}
          </Badge>
        ))}
        <Badge variant={src.local ? "cyan" : "neutral"}>
          {src.local ? `🌏 ${src.label}` : src.label}
        </Badge>
        {post.posted_at && (
          <time className="ml-auto shrink-0 font-mono text-xs text-white/45">
            {relativeTime(post.posted_at)}
          </time>
        )}
      </div>
      <h3 className="mt-2.5 line-clamp-2 text-sm font-medium leading-snug text-white">
        {post.title}
      </h3>
      {post.snippet && post.snippet !== post.title && (
        <p className="mt-1 line-clamp-2 text-[13px] leading-relaxed text-white/55">
          {post.snippet}
        </p>
      )}
    </div>
  );

  // 有原文連結 → 整卡可點（新分頁開啟，不奪走站內導覽）。
  return post.url ? (
    <a
      href={post.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block transition-opacity hover:opacity-80"
    >
      {body}
    </a>
  ) : (
    body
  );
}
