import Link from "next/link";

import { SectionStatus } from "@/components/section-status";
import { getModelDashboard } from "@/lib/api";

/** 左側「依模型瀏覽」側欄 —— 6 模型精簡垂直列表，點進詳情頁。自帶 fetch。 */
export async function ModelRail() {
  const models = await getModelDashboard();
  if (!models.ok) {
    return <SectionStatus kind="error">模型清單暫時載入不了，稍後再試。</SectionStatus>;
  }

  return (
    <nav aria-label="依模型瀏覽" className="space-y-0.5">
      <h2 className="mb-2 px-2 text-[13px] font-semibold tracking-tight text-ink/70">依模型瀏覽</h2>
      {models.data.map((m) => (
        <Link
          key={m.slug}
          href={`/models/${m.slug}`}
          className="group flex items-center gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-bg-cardLight"
        >
          {m.spike_severity != null && (
            <span
              title="近期討論升溫"
              className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent-primary"
              aria-hidden
            />
          )}
          <span className="truncate text-sm text-ink/75 group-hover:text-ink">{m.name}</span>
          <span className="ml-auto shrink-0 font-mono text-[11px] tabular-nums text-ink/70">
            {m.posts_total.toLocaleString()}
          </span>
        </Link>
      ))}
    </nav>
  );
}
