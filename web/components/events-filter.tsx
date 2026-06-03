"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";

import { cn } from "@/lib/utils";

const TYPES = [
  { value: "", label: "全部" },
  { value: "discussion_spike", label: "討論突增" },
  { value: "launch", label: "新發布" },
  { value: "sentiment_flip", label: "口碑翻轉" },
] as const;

const MODELS = [
  { value: "", label: "全部模型" },
  { value: "gpt", label: "GPT" },
  { value: "claude", label: "Claude" },
  { value: "gemini", label: "Gemini" },
  { value: "grok", label: "Grok" },
  { value: "llama", label: "Llama" },
  { value: "deepseek", label: "DeepSeek" },
];

/**
 * 事件流篩選列（事件類型 + 模型）。把選擇寫進 URL searchParams，
 * 首頁的 EventsFeed（Server Component）依 params 重新抓 → 純 URL 狀態、可分享、可後退。
 */
export function EventsFilter() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const type = params.get("type") ?? "";
  const model = params.get("model") ?? "";

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value);
    else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  return (
    <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-2">
      <div className="flex flex-wrap items-center gap-1.5">
        {TYPES.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => setParam("type", t.value)}
            aria-pressed={type === t.value}
            className={cn(
              "rounded-md border px-2.5 py-1 text-[12px] transition-colors",
              type === t.value
                ? "border-accent-primary/50 bg-accent-primary/10 text-ink"
                : "border-border/60 text-ink/55 hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <label className="ml-auto flex items-center gap-1.5 text-[12px] text-ink/50">
        模型
        <select
          value={model}
          onChange={(e) => setParam("model", e.target.value)}
          className="rounded-md border border-border/60 bg-bg px-2 py-1 text-[12px] text-ink"
        >
          {MODELS.map((m) => (
            <option key={m.value} value={m.value}>
              {m.label}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
