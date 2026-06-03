// API DTO 型別（與後端 /api 回傳對應的單一來源）。

export type ReleaseSource = "huggingface" | "github";

export interface ReleaseEvent {
  id: number;
  source: ReleaseSource;
  model: string | null;
  title: string;
  repo: string;
  kind: string;
  version: string | null;
  url: string;
  published_at: string; // ISO 8601
}

export interface ModelSummary {
  slug: string;
  name: string;
  company: string;
  role: string | null;
  posts_total: number;
  posts_recent: number;
  releases_total: number;
  latest_release_at: string | null;
  spike_severity: number | null;
  sentiment_index: number | null; // 口碑淨值 -100..100（情緒分析）
}

export interface DecideModel {
  slug: string;
  name: string;
  sentiment_index: number | null;
  posts_total: number;
  posts_recent: number;
  top_discussions: { title: string; score: number; url: string | null; source: string }[];
}

export interface DecideReport {
  topic: string | null;
  models: DecideModel[];
  recommendation: { winner: string | null; reason: string };
  summary: string;
  generated_by: "data" | "llm";
}

export interface TrendPoint {
  date: string; // ISO date (YYYY-MM-DD)
  posts: number;
  sentiment_index: number | null;
}

export interface ModelDetail extends ModelSummary {
  trend_days: number;
  trend: TrendPoint[];
  events: DetectedEvent[];
  top_discussions: { title: string; score: number; url: string | null; source: string }[];
  releases: ReleaseEvent[];
}

// ---- 每日實用情報 feed（定位 C 首頁核心）----

export type ThemeLabel = "新工具" | "使用方法" | "邊界";
export type Sentiment = "positive" | "neutral" | "negative";

export interface FeedPost {
  id: number;
  title: string;
  snippet: string;
  source: string;
  url: string | null;
  models: string[];
  sentiment: Sentiment | null; // null = 未分析
  theme: string;
  theme_confidence: number;
  score: number;
  posted_at: string | null;
}

// /api/feed 回傳：{ 主題: [貼文卡, ...] }
export type FeedThemes = Record<string, FeedPost[]>;
// /api/feed/summary 回傳：{ 主題: 計數 }
export type FeedSummary = Record<string, number>;

export interface TrendingKeyword {
  term: string;
  rank: number;
  z: number;
  recent_count: number;
}

export interface FeedFilters {
  model?: string;
  sentiment?: Sentiment;
  source?: string;
  days?: number;
}

export type EventType = "discussion_spike" | "launch" | "sentiment_flip";

// 注意：命名為 DetectedEvent 以避開瀏覽器全域 Event 型別。
export interface DetectedEvent {
  id: number;
  event_type: EventType;
  model: string | null;
  title: string;
  description: string | null;
  score: number | null;
  occurred_at: string; // ISO 8601
  extra: Record<string, unknown>;
}
