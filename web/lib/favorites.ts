import type { EventSummary, FeedPost } from "@/lib/types";

/**
 * 我的最愛 —— 純前端 localStorage 留存（N=1，無需後端/登入）。
 * 存整個貼文物件 → 即使該貼文滾出本週視窗，最愛仍在（跨週留存）。
 */
const KEY = "pulse:favorites";
export const FAVORITES_EVENT = "pulse:favorites-changed";

export function getFavorites(): FeedPost[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    return Array.isArray(raw) ? (raw as FeedPost[]) : [];
  } catch {
    return [];
  }
}

export function isFavorite(id: number): boolean {
  return getFavorites().some((p) => p.id === id);
}

/**
 * 事件 key（字串 id）→ 穩定數字 id：FNV-1a 32-bit 雜湊取負。
 * 收藏結構以 FeedPost.id（number）為鍵 —— 事件用負數空間，與貼文的正數 id 永不相撞。
 */
function eventNumericId(key: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < key.length; i++) {
    h ^= key.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return -(h >>> 0) - 1; // -1 起跳（雜湊 0 也不會撞到貼文 id 0）
}

/**
 * 把「今日事件」轉成可收藏 / 可進材料包的 FeedPost 形狀（純函式，server/client 皆可）：
 * id=事件 key 雜湊（負數）、title=事件標題、snippet=忠實摘要＋引註出處清單。
 * 後端材料包端點（PackPost）只取這些欄位的子集，負數 id 與「今日事件」來源都相容。
 */
export function eventToFavoritePost(ev: EventSummary): FeedPost {
  const cited = ev.citations.filter((c) => c.url);
  const sources = cited.map((c) => `[${c.n}] ${c.url}`).join(" ");
  return {
    id: eventNumericId(ev.id),
    title: ev.title,
    title_zh: null,
    snippet: sources ? `${ev.summary}\n出處：${sources}` : ev.summary,
    snippet_zh: null,
    source: "今日事件",
    url: cited[0]?.url ?? null,
    models: [],
    sentiment: null,
    theme: ev.theme,
    theme_confidence: 1, // 事件摘要本身就是高信心聚合產物
    score: ev.memberCount,
    posted_at: null, // 事件無單一發文時間（成員貼文各自有）；不假裝有
  };
}

/** 切換最愛狀態。回傳切換後是否為最愛。會發事件讓其他元件同步。 */
export function toggleFavorite(post: FeedPost): boolean {
  const cur = getFavorites();
  const exists = cur.some((p) => p.id === post.id);
  const next = exists ? cur.filter((p) => p.id !== post.id) : [post, ...cur];
  localStorage.setItem(KEY, JSON.stringify(next));
  window.dispatchEvent(new Event(FAVORITES_EVENT));
  return !exists;
}
