import { FavoriteButton } from "@/components/favorite-button";
import { NewBadge } from "@/components/new-badge";
import { sourceMeta } from "@/components/source-meta";
import { Badge } from "@/components/ui/badge";
import { relativeTime } from "@/lib/time";
import type { FeedPost, Sentiment } from "@/lib/types";

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
  const src = sourceMeta(post.source);
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
      {/* 收藏鈕命中區擴到 44px（FavoriteButton 內處理），位置微調 + 右側留 36px 淨空避免與徽章列重疊。 */}
      <FavoriteButton post={post} className="absolute right-1.5 top-1.5 z-10" />
      <div className="flex items-center gap-1.5 pr-9">
        <SentimentDot s={post.sentiment} />
        {post.models.map((m) => (
          <Badge key={m} variant="accent">
            {m}
          </Badge>
        ))}
        <Badge className={src.badge} title={src.local ? "中文在地來源" : `來源：${src.label}`}>
          <span aria-hidden>{src.emoji}</span>
          {src.label}
        </Badge>
        {/* NEW：晚於上次來訪的內容（client 子元件，首次來訪無基準不標）。 */}
        <NewBadge time={post.posted_at} />
      </div>
      <h3 className="mt-2.5 line-clamp-2 text-sm font-medium leading-snug text-ink">
        {post.title_zh ?? post.title}
      </h3>
      {/* 中英並列：有譯文時，原文以小字斜體列於下方對照 */}
      {post.title_zh && (
        <p className="mt-1 line-clamp-1 text-[11px] italic leading-snug text-ink/55">{post.title}</p>
      )}
      {(post.snippet_zh ?? post.snippet) && (post.snippet_zh ?? post.snippet) !== post.title && (
        <p className="mt-1.5 line-clamp-2 text-[13px] leading-relaxed text-ink/70">
          {post.snippet_zh ?? post.snippet}
        </p>
      )}
      {post.posted_at && (
        <time className="mt-2 block font-mono text-[11px] text-ink/70">
          {relativeTime(post.posted_at)}
        </time>
      )}
    </div>
  );
}
