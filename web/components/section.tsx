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
      <h2 className="text-[17px] font-semibold tracking-tight text-ink">{label}</h2>
      {description && <p className="mt-1.5 mb-5 text-sm leading-relaxed text-ink/45">{description}</p>}
      {!description && <div className="mb-5" />}
      {children}
    </section>
  );
}
