"use client";

import { useEffect, useState } from "react";

import { FeedCard } from "@/components/feed-card";
import { FAVORITES_EVENT, getFavorites } from "@/lib/favorites";
import type { FeedPost } from "@/lib/types";

/** 我的最愛清單（client，讀 localStorage）。跨週留存，與卡片愛心同步。 */
export function FavoritesList() {
  const [favs, setFavs] = useState<FeedPost[]>([]);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const sync = () => setFavs(getFavorites());
    sync();
    setReady(true);
    window.addEventListener(FAVORITES_EVENT, sync);
    return () => window.removeEventListener(FAVORITES_EVENT, sync);
  }, []);

  if (!ready) return null; // 避免 SSR/CSR 不一致閃爍
  if (favs.length === 0) {
    return (
      <p className="rounded-xl border border-dashed border-border px-6 py-10 text-center text-sm text-ink/40">
        還沒有最愛 —— 在情報卡片右上角點 ♥ 收藏，這裡會留著（每週清空不影響）。
      </p>
    );
  }
  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {favs.map((p) => (
        <FeedCard key={p.id} post={p} />
      ))}
    </div>
  );
}
