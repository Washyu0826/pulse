import type { FeedPost } from "@/lib/types";

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

/** 切換最愛狀態。回傳切換後是否為最愛。會發事件讓其他元件同步。 */
export function toggleFavorite(post: FeedPost): boolean {
  const cur = getFavorites();
  const exists = cur.some((p) => p.id === post.id);
  const next = exists ? cur.filter((p) => p.id !== post.id) : [post, ...cur];
  localStorage.setItem(KEY, JSON.stringify(next));
  window.dispatchEvent(new Event(FAVORITES_EVENT));
  return !exists;
}
