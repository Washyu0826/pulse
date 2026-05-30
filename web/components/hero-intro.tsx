/** 首頁開場：一句價值主張 + 它在做什麼 + 範圍（5 秒看懂）。 */
export function HeroIntro() {
  return (
    <section className="border-b border-border/60 pb-8">
      <h1 className="text-xl font-semibold tracking-tight text-white sm:text-2xl">
        AI 模型的即時動態，一眼掌握
      </h1>
      <p className="mt-2 max-w-2xl text-sm leading-relaxed text-white/65">
        Pulse 自動追蹤 HackerNews、Dev.to、HuggingFace、GitHub，偵測{" "}
        <span className="text-white/85">討論突增</span> 與{" "}
        <span className="text-white/85">新版發布</span>，每天 5 分鐘掌握 AI 圈，不用自己一個個網站翻。
      </p>
      <p className="mt-3 font-mono text-xs text-white/40">
        追蹤 6 個模型 · 5 個來源 · 過去 30 天
      </p>
    </section>
  );
}
