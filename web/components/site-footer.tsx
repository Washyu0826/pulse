import { Logo } from "@/components/logo";

/** 安靜的頁尾。 */
export function SiteFooter() {
  return (
    <footer className="flex w-full items-center gap-2 border-t border-border px-6 py-10 text-xs text-ink/40 lg:px-10 xl:px-16">
      <Logo />
      <span className="ml-1">· Data Project · 冼冠宇 · Xchange</span>
    </footer>
  );
}
