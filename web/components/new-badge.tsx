"use client";

import { useEffect, useState } from "react";

import { getLastVisitBaseline } from "@/lib/last-visit";

/**
 * NEW 小徽章（client 子元件）：貼文時間晚於「上次來訪」基準才顯示。
 * FeedCard 是 Server Component → 只把這顆小徽章切成 client，邏輯全在掛載後跑
 * （SSR / 首次 render 一律不顯示，避免 hydration 不一致；首次來訪無基準也不標）。
 */
export function NewBadge({ time }: { time: string | null }) {
  const [isNew, setIsNew] = useState(false);

  useEffect(() => {
    if (!time) return;
    const baseline = getLastVisitBaseline();
    if (baseline === null) return;
    const t = new Date(time).getTime();
    if (!Number.isNaN(t) && t > baseline) setIsNew(true);
  }, [time]);

  if (!isNew) return null;
  return (
    <span
      title="上次來訪之後的新內容"
      className="shrink-0 rounded border border-accent-primary/30 bg-accent-primary/10 px-1 font-mono text-[9px] font-medium uppercase tracking-wider text-accent-primary"
    >
      NEW
    </span>
  );
}
