import { FavoriteButton } from "@/components/favorite-button";
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
    return <span title="情緒未分析" className="h-2 w-2 shrink-0 rounded-full bg-ink/20" />;
  }
  const d = SENTIMENT_DOT[s];
  return <span title={`情緒：${d.word}`} className={`h-2 w-2 shrink-0 rounded-full ${d.cls}`} />;
}

/**
 * 單則實用情報卡片。整卡可點（stretched link 開原文）+ 右上角收藏愛心（client，浮在連結之上）。
 */
export function FeedCard({ post }: { post: FeedPost }) {
  const src = SOURCE_META[post.source] ?? { label: post.source };
  return (
    <div className="card-interactive relative h-full">
      {/* 整卡可點：覆蓋全卡的隱形連結（最愛按鈕 z 較高、不被它蓋住）。 */}
      {post.url && (
        <a
          href={post.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={post.title}
          className="absolute inset-0 z-0 rounded-xl"
        />
      )}
      <FavoriteButton post={post} className="absolute right-2.5 top-2.5 z-10" />
      <div className="flex items-center gap-1.5 pr-7">
        <SentimentDot s={post.sentiment} />
        {post.models.map((m) => (
          <Badge key={m} variant="accent">
            {m}
          </Badge>
        ))}
        <Badge variant={src.local ? "cyan" : "neutral"}>
          {src.local ? `🌏 ${src.label}` : src.label}
        </Badge>
      </div>
      <h3 className="mt-2.5 line-clamp-2 text-sm font-medium leading-snug text-ink">
        {post.title_zh ?? post.title}
      </h3>
      {/* 中英並列：有譯文時，原文以小字斜體列於下方對照 */}
      {post.title_zh && (
        <p className="mt-1 line-clamp-1 text-[11px] italic leading-snug text-ink/40">{post.title}</p>
      )}
      {(post.snippet_zh ?? post.snippet) && (post.snippet_zh ?? post.snippet) !== post.title && (
        <p className="mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-ink/55">
          {post.snippet_zh ?? post.snippet}
        </p>
      )}
      {post.posted_at && (
        <time className="mt-2 block font-mono text-[11px] text-ink/40">
          {relativeTime(post.posted_at)}
        </time>
      )}
    </div>
  );
}
