import type { ReactNode } from "react";

/** 區塊外殼：統一的小標題 + 內容。 */
export function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="mb-3 font-mono text-xs font-medium uppercase tracking-[0.12em] text-white/55">
        {label}
      </h2>
      {children}
    </section>
  );
}
