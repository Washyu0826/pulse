import { API_URL } from "@/lib/utils";
import type {
  DecideReport,
  DetectedEvent,
  EventType,
  ModelDetail,
  ModelSummary,
  ReleaseEvent,
} from "@/lib/types";

// 真正的 result type：失敗分支不帶 data，TS 會強制呼叫端先檢查 ok 才能用 data。
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

// 這些 wrapper 只在 server 端執行：優先用內部位址（容器網路），退回對外位址。
// （日後若有 Client Component 也打這支 API，client 端會用 NEXT_PUBLIC_API_URL。）
const BASE = process.env.API_URL_INTERNAL || API_URL;

/**
 * 共用的「抓 JSON 陣列」helper（Server Component 用）。
 * 任何失敗（網路、非 2xx、回應非陣列）都回 { ok: false }，絕不 throw 整個 route。
 */
async function fetchArray<T>(path: string): Promise<ApiResult<T[]>> {
  try {
    // ISR：最多每 60 秒在背景重新生成（顯式指定，避免 Next 版本預設行為改變）。
    const res = await fetch(`${BASE}${path}`, { next: { revalidate: 60 } });
    if (!res.ok) {
      console.error(`[api] ${path} HTTP ${res.status}`);
      return { ok: false, error: `HTTP ${res.status}` };
    }
    const json: unknown = await res.json();
    if (!Array.isArray(json)) {
      console.error(`[api] ${path} 回應不是陣列`);
      return { ok: false, error: "malformed response" };
    }
    return { ok: true, data: json as T[] };
  } catch (err) {
    console.error(`[api] ${path} fetch failed`, err);
    return { ok: false, error: String(err) };
  }
}

type ReleaseSourceFilter = "huggingface" | "github";

/** 最近的 release 事件（HF + GitHub），可選來源過濾。 */
export function getRecentReleases(
  limit = 20,
  source?: ReleaseSourceFilter,
): Promise<ApiResult<ReleaseEvent[]>> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (source) q.set("source", source);
  return fetchArray<ReleaseEvent>(`/api/releases/recent?${q.toString()}`);
}

/** 最近偵測到的事件，可選事件類型 / 模型 slug 過濾。 */
export function getRecentEvents(
  limit = 15,
  filters?: { eventType?: EventType; model?: string },
): Promise<ApiResult<DetectedEvent[]>> {
  const q = new URLSearchParams({ limit: String(limit) });
  if (filters?.eventType) q.set("event_type", filters.eventType);
  if (filters?.model) q.set("model", filters.model);
  return fetchArray<DetectedEvent>(`/api/events?${q.toString()}`);
}

/** 6 模型即時看板彙總。 */
export function getModelDashboard(): Promise<ApiResult<ModelSummary[]>> {
  return fetchArray<ModelSummary>(`/api/models`);
}

/** 單一模型詳情（趨勢 + 事件 + 熱門討論 + 發布）。404 → { ok:false }。 */
export async function getModelDetail(
  slug: string,
  trendDays = 30,
): Promise<ApiResult<ModelDetail>> {
  try {
    const res = await fetch(`${BASE}/api/models/${encodeURIComponent(slug)}?trend_days=${trendDays}`, {
      next: { revalidate: 60 },
    });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    return { ok: true, data: (await res.json()) as ModelDetail };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}

/** 決策報告（資料驅動模型比較）。 */
export async function getDecideReport(
  models: string,
  topic?: string,
): Promise<ApiResult<DecideReport>> {
  const q = new URLSearchParams({ models });
  if (topic) q.set("topic", topic);
  try {
    const res = await fetch(`${BASE}/api/decide?${q.toString()}`, { next: { revalidate: 60 } });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    return { ok: true, data: (await res.json()) as DecideReport };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}
