import { SiteHeader } from "@/components/site-header";
import { CardGridSkeleton, Skeleton } from "@/components/ui/skeleton";

/** 產品洞察 dashboard 導航載入骨架（與頁面區塊版型對齊）。 */
export default function Loading() {
  return (
    <>
      <SiteHeader />
      <main className="w-full px-6 py-12 lg:px-10 xl:px-16">
        <Skeleton className="h-8 w-44" />
        <Skeleton className="mt-3 h-4 w-96 max-w-full" />

        <div className="mt-10">
          <Skeleton className="h-5 w-24" />
          <div className="mt-5">
            <CardGridSkeleton count={4} cols={2} />
          </div>
        </div>

        <div className="mt-12 grid gap-8 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-xl" />
          <Skeleton className="h-72 w-full rounded-xl" />
        </div>

        <div className="mt-12 grid gap-8 lg:grid-cols-[1fr_280px]">
          <Skeleton className="h-64 w-full rounded-lg" />
          <Skeleton className="h-64 w-full rounded-lg" />
        </div>
      </main>
    </>
  );
}
