import { SiteHeader } from "@/components/site-header";
import { Skeleton } from "@/components/ui/skeleton";

/** 模型詳情頁載入骨架。 */
export default function Loading() {
  return (
    <>
      <SiteHeader />
      <main className="mx-auto max-w-4xl space-y-8 px-6 py-10">
        <div>
          <Skeleton className="h-3 w-20" />
          <Skeleton className="mt-4 h-8 w-48" />
          <Skeleton className="mt-3 h-4 w-80" />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-32 w-full rounded-lg" />
        <Skeleton className="h-20 w-full rounded-lg" />
      </main>
    </>
  );
}
