"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { SOURCE_META, SOURCE_ORDER } from "@/components/source-meta";
import { buildFilterParams } from "@/lib/feed-filter-url";
import { MODELS as MODEL_LIST } from "@/lib/site";
import { cn } from "@/lib/utils";

// 模型 chip 選項由 lib/site 的 MODELS 單一來源衍生（+ 前置「全部」）。
const MODELS = [
  { value: "", label: "全部" },
  ...MODEL_LIST.map((m) => ({ value: m.slug, label: m.name })),
];
const SENTIMENTS = [
  { value: "", label: "全部" },
  { value: "positive", label: "🟢 正面" },
  { value: "negative", label: "🔴 負面" },
];
// 來源選項由 source-meta 的 SOURCE_ORDER 衍生，新增來源只需改一處。
const SOURCES = [
  { value: "", label: "全部" },
  ...SOURCE_ORDER.map((s) => ({
    value: s,
    label: `${SOURCE_META[s].emoji} ${SOURCE_META[s].label}`,
  })),
];
const DAYS = [
  { value: "1", label: "今日" },
  { value: "7", label: "本週" },
  { value: "30", label: "近 30 天" },
  { value: "90", label: "近 90 天" },
];

/**
 * 實用情報篩選列（模型 chip + 情緒/來源/時間 下拉）。寫進 URL searchParams →
 * 首頁的 ThemeFeed / FeedSummary（Server Component）依 params 重抓 → 純 URL 狀態、可分享。
 */
export function FeedFilter() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const model = params.get("model") ?? "";

  function setParam(key: string, value: string) {
    const next = buildFilterParams(params.toString(), key, value);
    // push（非 replace）：每次篩選變更留歷史紀錄 → 按上一頁可逐步退回，符合「可後退」設計。
    router.push(`${pathname}?${next}`, { scroll: false });
  }

  const select = (key: string, opts: { value: string; label: string }[], fallback = "") => (
    <select
      value={params.get(key) ?? fallback}
      onChange={(e) => setParam(key, e.target.value)}
      // 行動端 16px：iOS Safari 在表單控制項 <16px 時聚焦會強制整頁縮放（sm 以上維持 12px 緊湊）。
      className="rounded-md border border-border/60 bg-bg px-2 py-1 text-base text-ink sm:text-[12px]"
    >
      {opts.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );

  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {MODELS.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => setParam("model", m.value)}
            aria-pressed={model === m.value}
            className={cn(
              "rounded-md border px-2.5 py-1 text-[12px] transition-colors",
              model === m.value
                ? "border-accent-primary/50 bg-accent-primary/10 text-ink"
                : "border-border/60 text-ink/70 hover:text-ink",
            )}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-2 text-[12px] text-ink/50">
        <label className="flex items-center gap-1.5">情緒{select("sentiment", SENTIMENTS)}</label>
        <label className="flex items-center gap-1.5">來源{select("source", SOURCES)}</label>
        <label className="flex items-center gap-1.5">時間{select("days", DAYS, "1")}</label>
      </div>
    </div>
  );
}
