import type { ReactNode } from "react";

/** 區塊的「載入失敗 / 無資料」狀態框（與卡片同表面，消除重複）。 */
export function SectionStatus({ kind, children }: { kind: "error" | "empty"; children: ReactNode }) {
  const color = kind === "error" ? "text-sentiment-negative" : "text-white/55";
  return (
    <div className={`card flex items-center justify-center py-8 text-center text-sm ${color}`}>
      {children}
    </div>
  );
}
