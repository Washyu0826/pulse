"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";

/**
 * 「回上頁」（client）：用 router.back() 回到來頁 —— 從已篩選的首頁/主題頁點進來，
 * 退回時篩選狀態原封不動（修掉舊版寫死 href="/" 導致篩選歸零的問題）。
 * 直接落地本頁（無站內歷史）時退回首頁，不會把人彈出站外。
 */
export function BackLink({ label = "回上頁" }: { label?: string }) {
  const router = useRouter();
  return (
    <button
      type="button"
      onClick={() => {
        if (window.history.length > 1) router.back();
        else router.push("/");
      }}
      className="inline-flex items-center gap-1 text-xs text-ink/50 transition-colors hover:text-ink"
    >
      <ArrowLeft className="h-3.5 w-3.5" aria-hidden />
      {label}
    </button>
  );
}
