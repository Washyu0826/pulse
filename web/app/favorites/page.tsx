/** 我的最愛頁 —— 前端 localStorage 留存的收藏貼文（跨週不清空）。 */
import { FavoritesList } from "@/components/favorites-list";
import { SiteFooter } from "@/components/site-footer";
import { SiteHeader } from "@/components/site-header";

export const metadata = { title: "我的最愛 · Pulse" };

export default function FavoritesPage() {
  return (
    <>
      <SiteHeader />
      <main className="w-full px-6 py-12 lg:px-10 xl:px-16">
        <h1 className="text-2xl font-semibold tracking-tight text-ink">我的最愛</h1>
        <p className="mb-8 mt-1.5 text-sm text-ink/45">
          你收藏的情報，存在這台瀏覽器、跨週留存（每週清空只影響首頁的本週情報）。
        </p>
        <FavoritesList />
      </main>
      <SiteFooter />
    </>
  );
}
