import { THEME_META, THEME_ORDER } from "@/components/theme-meta";

/**
 * 首頁開場（定位 C）：一句價值主張 + 跟電子報差在哪 + 三主題（5 秒看懂這是什麼、為何有用）。
 */
export function HeroIntro() {
  return (
    <section className="border-b border-border/60 pb-8">
      <h1 className="text-xl font-semibold tracking-tight text-white sm:text-[26px] sm:leading-tight">
        每天的 AI 實用情報，<span className="text-accent-primary">一頁掌握</span>
      </h1>
      <p className="mt-2.5 max-w-2xl text-sm leading-relaxed text-white/65">
        自動爬梳技術社群與
        <span className="text-accent-cyan">中文 Threads</span>，把大家正在討論的整理成三類：
        <span className="text-white/85">新工具、怎麼用、要注意的坑</span>。
      </p>
      <p className="mt-1.5 max-w-2xl text-[13px] leading-relaxed text-white/45">
        過濾雜訊、可依模型與情緒篩選 —— 不是電子報塞給你，是
        <span className="text-white/65">能查的結構化情報</span>。
      </p>

      <ul className="mt-5 grid gap-3 sm:grid-cols-3">
        {THEME_ORDER.map((label) => {
          const m = THEME_META[label];
          return (
            <li
              key={label}
              className="rounded-lg border border-border/50 bg-bg-card/50 p-3.5 transition-colors hover:border-border"
            >
              <div className="flex items-center gap-2">
                <span className={`flex h-7 w-7 items-center justify-center rounded-md ${m.bg} ${m.text}`}>
                  <m.Icon className="h-4 w-4" />
                </span>
                <span className="text-sm font-medium text-white/90">{label}</span>
              </div>
              <p className="mt-2 text-[12px] leading-relaxed text-white/50">{m.blurb}</p>
            </li>
          );
        })}
      </ul>

      <p className="mt-5 font-mono text-xs text-white/40">
        6 模型 · HN / Dev.to / <span className="text-accent-cyan/70">🌏 中文 Threads</span> · 約 5,000 篇 · 過濾雜訊後
      </p>
    </section>
  );
}
