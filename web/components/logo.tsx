import { cn } from "@/lib/utils";

/**
 * Pulse logo —— 藍色圓角方塊內一條脈搏波形（呼應 "Pulse" / 監測情報），加 wordmark。
 * 純展示；外層自行包 <Link>。
 */
export function Logo({ className, markOnly = false }: { className?: string; markOnly?: boolean }) {
  return (
    <span className={cn("inline-flex items-center gap-2", className)}>
      <span className="animate-pulse-beat flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-accent-primary shadow-sm shadow-accent-primary/30">
        <svg
          viewBox="0 0 24 24"
          className="h-[18px] w-[18px]"
          fill="none"
          stroke="white"
          strokeWidth={2.2}
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden
        >
          <path d="M1 12 H6 L8.5 5 L12.5 19 L15 12 H23" />
        </svg>
      </span>
      {!markOnly && (
        <span className="font-script text-[26px] font-bold leading-none text-ink">Pulse</span>
      )}
    </span>
  );
}
