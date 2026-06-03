import { HelpCircle } from "lucide-react";

/**
 * 行內「這是什麼」提示 —— 在白話標籤旁放一個小問號，hover/focus 顯示真正的指標定義。
 * 純 CSS（group-hover + focus-within），無 client JS，可在 Server Component 使用。
 * a11y：button 帶 aria-label，tooltip 內容也放進 sr-only 供讀屏。
 */
export function InfoHint({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <span className="group relative inline-flex items-center align-middle">
      <button
        type="button"
        aria-label={`${label}：說明`}
        className="inline-flex items-center text-ink/35 transition-colors hover:text-ink/70 focus-visible:text-ink/70"
      >
        <HelpCircle className="h-3.5 w-3.5" aria-hidden />
      </button>
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 rounded-md border border-border bg-bg-cardLight px-3 py-2 text-left text-[12px] font-normal normal-case leading-relaxed tracking-normal text-ink/80 opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 group-focus-within:opacity-100"
      >
        {children}
      </span>
    </span>
  );
}
