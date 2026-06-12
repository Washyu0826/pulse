"use client";

import { Heart } from "lucide-react";
import { useEffect, useState } from "react";

import { FAVORITES_EVENT, isFavorite, toggleFavorite } from "@/lib/favorites";
import type { FeedPost } from "@/lib/types";
import { cn } from "@/lib/utils";

/** 收藏愛心（client，localStorage）。放在卡片上層，點擊不觸發底下的連結。 */
export function FavoriteButton({ post, className }: { post: FeedPost; className?: string }) {
  const [fav, setFav] = useState(false);

  // 初次載入 + 跨元件同步（避免 SSR/CSR hydration 不一致 → 先 false，掛載後校正）。
  useEffect(() => {
    const sync = () => setFav(isFavorite(post.id));
    sync();
    window.addEventListener(FAVORITES_EVENT, sync);
    return () => window.removeEventListener(FAVORITES_EVENT, sync);
  }, [post.id]);

  return (
    <button
      type="button"
      aria-pressed={fav}
      aria-label={fav ? "移除最愛" : "加入最愛"}
      title={fav ? "移除最愛" : "加入最愛"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        setFav(toggleFavorite(post));
      }}
      className={cn(
        // 觸控命中區 ≥44px：視覺 p-2（32px）+ 透明外擴 6px 命中層 = 44px，
        // 不放大 icon 本身。z 高於整卡 stretched link（由呼叫端傳 z-10），
        // 點擊範圍內不會誤觸底下的外部連結。
        "relative rounded-md p-2 transition-colors before:absolute before:-inset-1.5 before:content-[''] hover:bg-accent-primary/10",
        fav ? "text-accent-primary" : "text-ink/45 hover:text-accent-primary",
        className,
      )}
    >
      <Heart className="h-4 w-4" fill={fav ? "currentColor" : "none"} aria-hidden />
    </button>
  );
}
