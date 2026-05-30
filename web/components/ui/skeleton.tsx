import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-white/[0.06]", className)} />;
}

function CardSkeleton({ compact }: { compact?: boolean }) {
  return (
    <div className="card">
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-16" />
        <Skeleton className="h-4 w-12" />
        <Skeleton className="ml-auto h-3 w-10" />
      </div>
      {compact ? (
        <Skeleton className="mt-3 h-7 w-20" />
      ) : (
        <>
          <Skeleton className="mt-3 h-4 w-3/4" />
          <Skeleton className="mt-2 h-3 w-1/2" />
        </>
      )}
    </div>
  );
}

/** 區塊載入骨架（與真實卡片同格線）。 */
export function CardGridSkeleton({
  count,
  cols,
  compact,
}: {
  count: number;
  cols: 2 | 6;
  compact?: boolean;
}) {
  const grid =
    cols === 2
      ? "grid gap-3 md:grid-cols-2"
      : "grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6";
  return (
    <div className={grid}>
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} compact={compact} />
      ))}
    </div>
  );
}
