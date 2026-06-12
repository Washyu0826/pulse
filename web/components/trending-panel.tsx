import { getTrending } from "@/lib/api";

/** 右側「本週熱詞」面板 —— log-odds 趨勢榜，每週滾動。自帶 fetch。 */
export async function TrendingPanel() {
  const trending = await getTrending(15);
  if (!trending.ok || trending.data.length === 0) {
    return null; // 熱詞非關鍵，失敗/空就不顯示
  }
  const max = Math.max(...trending.data.map((t) => t.recent_count), 1);

  return (
    <section aria-label="本週熱詞">
      <h2 className="mb-1 flex items-center gap-1.5 text-[13px] font-semibold tracking-tight text-ink/70">
        <span aria-hidden>🔥</span> 本週熱詞
      </h2>
      <p className="mb-3 text-[11px] text-ink/70">社群這週討論異常變多的詞（每週滾動）</p>
      <ol className="space-y-0.5">
        {trending.data.map((t) => (
          <li key={t.term}>
            <div className="group relative flex items-center gap-2 rounded-md px-2 py-1.5">
              {/* 熱度底條（依文章數比例，赭石淡色） */}
              <span
                aria-hidden
                className="absolute inset-y-0 left-0 rounded-md bg-accent-primary/[0.07]"
                style={{ width: `${(t.recent_count / max) * 100}%` }}
              />
              <span className="relative w-4 shrink-0 text-right font-mono text-[11px] text-ink/35">
                {t.rank}
              </span>
              <span className="relative truncate text-sm text-ink/80">{t.term}</span>
              <span className="relative ml-auto shrink-0 font-mono text-[11px] tabular-nums text-ink/70">
                {t.recent_count}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
