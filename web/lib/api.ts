import { API_URL } from "@/lib/utils";
import type {
  DecideReport,
  DetectedEvent,
  EventSummary,
  EventType,
  FeedFilters,
  FeedPost,
  FeedSummary,
  FeedThemes,
  ModelDetail,
  ModelSummary,
  ReleaseEvent,
  TrendingKeyword,
} from "@/lib/types";

// 真正的 result type：失敗分支不帶 data，TS 會強制呼叫端先檢查 ok 才能用 data。
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

// 這些 wrapper 只在 server 端執行：優先用內部位址（容器網路），退回對外位址。
// （日後若有 Client Component 也打這支 API，client 端會用 NEXT_PUBLIC_API_URL。）
const BASE = process.env.API_URL_INTERNAL || API_URL;

// 讀取類請求逾時上限：API 不通時不要懸掛 90 秒以上。
// 逾時 fetch 會 throw（TimeoutError）→ 走下面各 wrapper 既有的 { ok:false } 錯誤路徑。
const FETCH_TIMEOUT_MS = 10_000;

/**
 * 共用的「抓 JSON 陣列」helper（Server Component 用）。
 * 任何失敗（網路、非 2xx、回應非陣列）都回 { ok: false }，絕不 throw 整個 route。
 */
async function fetchArray<T>(path: string): Promise<ApiResult<T[]>> {
  try {
    // ISR：最多每 60 秒在背景重新生成（顯式指定，避免 Next 版本預設行為改變）。
    const res = await fetch(`${BASE}${path}`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
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

/** feed filters → query string（共用）。 */
function feedQuery(filters?: FeedFilters, extra?: Record<string, string>): string {
  const q = new URLSearchParams(extra);
  if (filters?.model) q.set("model", filters.model);
  if (filters?.sentiment) q.set("sentiment", filters.sentiment);
  if (filters?.source) q.set("source", filters.source);
  if (filters?.days) q.set("days", String(filters.days));
  return q.toString();
}

/**
 * 每日實用情報 feed：各主題 top N 貼文（回傳物件 {主題: [...]}，非陣列 → 自訂 fetch）。
 * 失敗回 { ok:false }，不 throw。
 */
export async function getFeed(
  filters?: FeedFilters,
  limitPerTheme = 6,
): Promise<ApiResult<FeedThemes>> {
  const qs = feedQuery(filters, { limit_per_theme: String(limitPerTheme) });
  try {
    const res = await fetch(`${BASE}/api/feed?${qs}`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    return { ok: true, data: (await res.json()) as FeedThemes };
  } catch (err) {
    console.error("[api] /api/feed fetch failed", err);
    return { ok: false, error: String(err) };
  }
}

/**
 * 單一主題的完整列表（主題列表頁 /theme/[label] 用）：
 * 後端 `?theme=` 只回該主題、量加大（limit_per_theme 上限 50）。
 * 注意：後端 Theme Literal 只收 5 個實用主題，「其他」/未知主題請在呼叫前兜底，不要打進來。
 */
export async function getThemeFeed(
  theme: string,
  filters?: FeedFilters,
  limit = 50,
): Promise<ApiResult<FeedPost[]>> {
  const qs = feedQuery(filters, { theme, limit_per_theme: String(limit) });
  try {
    const res = await fetch(`${BASE}/api/feed?${qs}`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    const json = (await res.json()) as FeedThemes;
    return { ok: true, data: json[theme] ?? [] };
  } catch (err) {
    console.error("[api] /api/feed (theme) fetch failed", err);
    return { ok: false, error: String(err) };
  }
}

/** 各主題在篩選下的貼文數（首頁今日摘要列）。 */
export async function getFeedSummary(filters?: FeedFilters): Promise<ApiResult<FeedSummary>> {
  try {
    const res = await fetch(`${BASE}/api/feed/summary?${feedQuery(filters)}`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` };
    return { ok: true, data: (await res.json()) as FeedSummary };
  } catch (err) {
    console.error("[api] /api/feed/summary fetch failed", err);
    return { ok: false, error: String(err) };
  }
}

/** 本週熱詞榜（log-odds 趨勢）。 */
export function getTrending(limit = 15): Promise<ApiResult<TrendingKeyword[]>> {
  return fetchArray<TrendingKeyword>(`/api/trending?limit=${limit}`);
}

/**
 * 今日事件：把多篇相關貼文聚成事件 + 忠實摘要（含行內出處引用）。
 * 後端端點 /api/events/today 可能尚未上線 → 失敗一律回 { ok:false }，UI 退回空狀態（不 throw）。
 */
export function getTodayEvents(limit = 8): Promise<ApiResult<EventSummary[]>> {
  return fetchArray<EventSummary>(`/api/events/today?limit=${limit}`);
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
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
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
    const res = await fetch(`${BASE}/api/decide?${q.toString()}`, {
      next: { revalidate: 60 },
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
    });
    if (!res.ok) {
      return { ok: false, error: `HTTP ${res.status}` };
    }
    return { ok: true, data: (await res.json()) as DecideReport };
  } catch (err) {
    return { ok: false, error: String(err) };
  }
}
