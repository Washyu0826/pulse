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
