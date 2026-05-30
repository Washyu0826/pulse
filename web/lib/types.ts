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
