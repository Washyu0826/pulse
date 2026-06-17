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

// 5 個實用主題 + 低信心 fallback「其他」（與 ml/ml/theme.py THEME_HYPOTHESES 對齊，2026-06 改版）。
// 後端可能回傳未知/舊主題字串 → 前端一律以「其他」兜底（見 theme-meta.tsx 的 themeMeta()）。
export type ThemeLabel = "新工具" | "模型動態" | "使用方法" | "風險限制" | "倫理法規" | "其他";
export type Sentiment = "positive" | "neutral" | "negative";

// 多來源語料的來源軸（與 DB 的 source 欄位對齊）。後端可能回傳其他/未知字串
// → 前端一律以中性樣式兜底（見 source-meta.tsx 的 sourceMeta()）。
export type SourceLabel = "hackernews" | "devto" | "threads" | "ptt" | "lobsters";

export interface FeedPost {
  id: number;
  title: string;
  title_zh: string | null; // 繁中譯文（英文貼才有）
  snippet: string;
  snippet_zh: string | null;
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

// ---- 今日事件（忠實摘要 + 行內出處引用）----

/** 一筆出處引用：對應摘要中的 [n] 標記，連向原貼文。 */
export interface EventCitation {
  n: number; // 摘要中的引用序號（[1][2]…）
  url?: string; // 原貼文連結（可無）
  postId?: string; // 成員貼文 id（無 url 時可用）
}

/** 一則「今日事件」：把多篇相關貼文聚成一個事件，附忠實摘要與行內出處。 */
export interface EventSummary {
  id: string;
  title: string;
  summary: string; // 摘要文字，內含 [1][2] 行內引用標記
  citations: EventCitation[];
  memberCount: number; // 此事件涵蓋的成員貼文數
  theme: ThemeLabel;
}

// ---- 產品洞察 dashboard 時序（GET /api/dashboard/trends?days=N）----

/** 逐日各主題貼文數（5 實用主題 + 其他）。date 為 YYYY-MM-DD。 */
export type ThemeTrendPoint = { date: string } & Record<ThemeLabel, number>;

/** 逐日情緒佔比（positive/neutral/negative 計數）。date 為 YYYY-MM-DD。 */
export interface SentimentTrendPoint {
  date: string;
  positive: number;
  neutral: number;
  negative: number;
}

/** /api/dashboard/trends 回傳：主題時序 + 情緒時序。端點可能尚未上線 → 失敗回 { ok:false }。 */
export interface DashboardTrends {
  theme_trend: ThemeTrendPoint[];
  sentiment_trend: SentimentTrendPoint[];
}

// ---- 議題時間軸（GET /api/storylines?limit=N）----

/** 議題鏈的當前狀態（與後端 ml/ml/hotness.py 狀態字串對齊）。 */
export type StorylineState = "升溫" | "高峰" | "退燒" | "持平";

/** 一筆議題出處引用：對應時間軸某日的代表貼文。 */
export interface StorylineCitation {
  n: number;
  url?: string | null;
  title?: string | null;
}

/** 議題時間軸某一天的一格：聲量走勢 + 一句重點 + 來源。 */
export interface TimelinePoint {
  date: string; // YYYY-MM-DD
  summary: string;
  volume: number; // 當日聲量（成員數 + log(1+互動)）
  velocity: number; // Δvolume（相對前一日）
  state: StorylineState;
  sentiment: Sentiment | null;
  sources: string[];
  members: number;
}

/** 一條議題時間軸：同議題的跨日事件鏈，含每日聲量走勢與升溫/退燒狀態。 */
export interface Storyline {
  id: string;
  title: string;
  state: StorylineState;
  hotness: number;
  spanDays: number; // 涵蓋的相異天數
  theme: ThemeLabel;
  timeline: TimelinePoint[];
  citations: StorylineCitation[];
}
