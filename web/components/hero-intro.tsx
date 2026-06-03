/** 首頁開場（定位 C）：精煉一句價值主張 + 一行差異化。下方緊接三主題欄，故不重複列舉。 */
export function HeroIntro() {
  return (
    <section className="pt-2">
      <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[34px] sm:leading-[1.15]">
        每天的 AI 實用情報，<span className="text-accent-primary">一頁掌握</span>
      </h1>
      <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink/60">
        爬梳技術社群與<span className="text-accent-primary">中文 Threads</span>，過濾雜訊後整理成
        <span className="text-ink/85"> 新工具、怎麼用、要注意的坑</span> —— 可依模型與情緒篩選的結構化情報。
      </p>
    </section>
  );
}
