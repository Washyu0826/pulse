import { API_URL } from "@/lib/utils";
import type { ReleaseEvent } from "@/lib/types";

// 真正的 result type：失敗分支不帶 data，TS 會強制呼叫端先檢查 ok 才能用 data。
export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: string };

// 這個 wrapper 只在 server 端執行：優先用內部位址（容器網路），退回對外位址。
// （日後若有 Client Component 也打這支 API，client 端會用 NEXT_PUBLIC_API_URL。）
const BASE = process.env.API_URL_INTERNAL || API_URL;

/**
 * 抓最近的 release 事件（Server Component 用）。
 *
 * 任何失敗（網路、非 2xx、回應非陣列）都回 { ok: false }，絕不 throw 整個 route。
 */
export async function getRecentReleases(limit = 20): Promise<ApiResult<ReleaseEvent[]>> {
  try {
    const res = await fetch(`${BASE}/api/releases/recent?limit=${limit}`, {
      // ISR：最多每 60 秒在背景重新生成（顯式指定，避免 Next 版本預設行為改變）。
      next: { revalidate: 60 },
    });
    if (!res.ok) {
      console.error(`[getRecentReleases] HTTP ${res.status}`);
      return { ok: false, error: `HTTP ${res.status}` };
    }
    const json: unknown = await res.json();
    if (!Array.isArray(json)) {
      // 200 但回傳非陣列（部分故障）→ 視為失敗，避免下游 .map crash。
      console.error("[getRecentReleases] 回應不是陣列");
      return { ok: false, error: "malformed response" };
    }
    return { ok: true, data: json as ReleaseEvent[] };
  } catch (err) {
    console.error("[getRecentReleases] fetch failed", err);
    return { ok: false, error: String(err) };
  }
}
