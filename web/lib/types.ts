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

export type EventType = "discussion_spike" | "launch";

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
