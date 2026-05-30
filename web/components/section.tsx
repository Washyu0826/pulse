import type { ReactNode } from "react";

/** 區塊外殼：小標題 + 一行「這是什麼」說明 + 內容。 */
export function Section({
  label,
  description,
  children,
}: {
  label: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h2 className="font-mono text-xs font-medium uppercase tracking-[0.12em] text-white/55">
        {label}
      </h2>
      {description && <p className="mt-1 mb-3 text-[13px] text-white/45">{description}</p>}
      {!description && <div className="mb-3" />}
      {children}
    </section>
  );
}
