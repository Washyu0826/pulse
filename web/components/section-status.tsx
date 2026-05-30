import type { ReactNode } from "react";

/** 區塊的「載入失敗 / 無資料」狀態框（沿用 placeholder 樣式，消除重複）。 */
export function SectionStatus({ kind, children }: { kind: "error" | "empty"; children: ReactNode }) {
  const color = kind === "error" ? "text-sentiment-negative" : "text-white/40";
  return (
    <div className={`bg-bg-card rounded-xl p-8 border border-border text-center ${color}`}>
      {children}
    </div>
  );
}
