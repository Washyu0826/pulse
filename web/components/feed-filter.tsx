"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

const MODELS = [
  { value: "", label: "全部" },
  { value: "claude", label: "Claude" },
  { value: "gpt", label: "GPT" },
  { value: "gemini", label: "Gemini" },
  { value: "grok", label: "Grok" },
  { value: "llama", label: "Llama" },
  { value: "deepseek", label: "DeepSeek" },
];
const SENTIMENTS = [
  { value: "", label: "全部" },
  { value: "positive", label: "🟢 正面" },
  { value: "negative", label: "🔴 負面" },
];
const SOURCES = [
  { value: "", label: "全部" },
  { value: "hackernews", label: "HN" },
  { value: "devto", label: "Dev.to" },
  { value: "threads", label: "🌏 Threads" },
];
const DAYS = [
  { value: "7", label: "近 7 天" },
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
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const select = (key: string, opts: { value: string; label: string }[], fallback = "") => (
    <select
      value={params.get(key) ?? fallback}
      onChange={(e) => setParam(key, e.target.value)}
      className="rounded-md border border-border/60 bg-bg px-2 py-1 text-[12px] text-ink"
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
                : "border-border/60 text-ink/55 hover:text-ink",
            )}
          >
            {m.label}
          </button>
        ))}
      </div>
      <div className="ml-auto flex flex-wrap items-center gap-x-3 gap-y-2 text-[12px] text-ink/50">
        <label className="flex items-center gap-1.5">情緒{select("sentiment", SENTIMENTS)}</label>
        <label className="flex items-center gap-1.5">來源{select("source", SOURCES)}</label>
        <label className="flex items-center gap-1.5">時間{select("days", DAYS, "30")}</label>
      </div>
    </div>
  );
}
