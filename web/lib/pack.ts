import { API_URL } from "@/lib/utils";
import type { FeedPost } from "@/lib/types";

/** 收藏知識材料包（後端 /api/collection/pack 回傳）。 */
export interface CollectionPack {
  markdown: string;
  sources_jsonl: string;
  themes: { theme: string; count: number; distilled: boolean }[];
  n_posts: number;
}

/**
 * 把選取的收藏送後端蒸成知識材料包（client 端呼叫 → 用 NEXT_PUBLIC_API_URL）。
 * distill=true 走地端 LLM；失敗時後端各主題自動退回確定性條列（仍會回 200）。
 */
// 蒸餾要等地端 LLM 逐主題生成，逾時放寬到 120 秒（一般讀取類是 10 秒）。
const PACK_TIMEOUT_MS = 120_000;

export async function generateCollectionPack(
  posts: FeedPost[],
  distill: boolean,
): Promise<CollectionPack> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}/api/collection/pack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ posts, distill, title: "收藏知識材料包" }),
      signal: AbortSignal.timeout(PACK_TIMEOUT_MS),
    });
  } catch (err) {
    // 逾時轉成友善訊息，走呼叫端既有的 throw → setError 錯誤路徑。
    if (err instanceof DOMException && err.name === "TimeoutError") {
      throw new Error("生成逾時（超過 120 秒）—— 後端可能正忙，請稍後再試或關閉 AI 蒸餾。");
    }
    throw err;
  }
  if (!res.ok) {
    const body: unknown = await res.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body ? String((body as { detail: unknown }).detail) : null;
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json() as Promise<CollectionPack>;
}

/** 觸發瀏覽器下載一段文字（UTF-8）。 */
export function downloadText(filename: string, text: string, mime = "text/markdown"): void {
  const blob = new Blob([text], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
