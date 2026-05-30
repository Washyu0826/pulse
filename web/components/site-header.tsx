import { LiveDot } from "@/components/live-dot";

/** 置頂導覽列 —— wordmark + 標語 + LIVE 指示。 */
export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-border/60 bg-bg/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-5xl items-center gap-3 px-6">
        <span className="text-xl font-semibold tracking-tight text-white">Pulse</span>
        <span className="hidden text-sm text-white/55 sm:inline">AI 工程師的每日情報秘書</span>
        <div className="ml-auto flex items-center gap-2 font-mono text-[11px] uppercase tracking-widest text-white/55">
          <LiveDot />
          Live
        </div>
      </div>
    </header>
  );
}
