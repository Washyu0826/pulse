import Link from "next/link";

import { LiveDot } from "@/components/live-dot";
import { Logo } from "@/components/logo";
import { SiteNav } from "@/components/site-nav";

/** 置頂導覽列 —— wordmark + 標語 + 導覽 + LIVE 指示。 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-bg/80 backdrop-blur-md">
      {/* ≤375px 溢出最小修法：窄螢幕收內距、藏 wordmark 與 Live 徽章（圖標+導覽必留），不做大改版。 */}
      <div className="flex h-14 w-full items-center gap-3 px-4 sm:px-6 lg:px-10 xl:px-16">
        <Link href="/" aria-label="Pulse 首頁">
          <Logo wordmarkClassName="hidden min-[400px]:inline" />
        </Link>
        <span className="hidden text-sm text-ink/50 sm:inline">每天的 AI 實用情報</span>
        <div className="ml-auto flex items-center gap-4">
          <SiteNav />
          <span className="hidden items-center gap-1.5 text-xs text-ink/45 min-[400px]:flex">
            <LiveDot />
            Live
          </span>
        </div>
      </div>
    </header>
  );
}
