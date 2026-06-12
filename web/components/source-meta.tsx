import type { SourceLabel } from "@/lib/types";

/**
 * 多來源語料的「來源軸」呈現中介資料（label + emoji + 配色）——
 * feed 卡片來源徽章、來源篩選器、摘要列共用。與 DB 的 source 欄位對齊。
 *
 * 與 2 色克制的「主題軸」不同：來源是次要維度且各來源有約定俗成的識別色
 * （HN 橘、PTT 綠、Threads 黑/在地、Dev.to 紫…），故各來源各自配色，
 * 用淡底 + 邊框小徽章呈現，不喧賓奪主。
 * 注意：class 字串需為字面量，Tailwind 才掃得到（勿動態拼接）。
 *
 * local=true 標記中文在地來源（Threads / PTT），凸顯定位 C 差異化。
 */
export interface SourceMeta {
  label: string;
  emoji: string;
  /** 徽章樣式（淡底 + 邊框 + 文字色）。 */
  badge: string;
  /** 是否為中文在地來源（Threads / PTT）。 */
  local?: boolean;
}

/** 中性兜底（未知來源用）。 */
const NEUTRAL: SourceMeta = {
  label: "其他",
  emoji: "•",
  badge: "border-border bg-ink/[0.03] text-ink/70",
};

// 文字色一律用 -700 階：-400/-500 是暗色主題的選擇，白底 10px 全數低於 WCAG AA 4.5:1
//（emerald-400 只有 1.9:1）。淡底 / 邊框維持 -500/10、-500/30，色相識別不變。
export const SOURCE_META: Record<SourceLabel, SourceMeta> = {
  hackernews: {
    label: "HN",
    emoji: "🟠",
    badge: "border-orange-500/30 bg-orange-500/10 text-orange-700",
  },
  devto: {
    label: "Dev.to",
    emoji: "👾",
    badge: "border-violet-500/30 bg-violet-500/10 text-violet-700",
  },
  threads: {
    label: "Threads",
    emoji: "🧵",
    badge: "border-accent-cyan/30 bg-accent-cyan/10 text-accent-strong",
    local: true,
  },
  ptt: {
    label: "PTT",
    emoji: "🟢",
    badge: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700",
    local: true,
  },
  lobsters: {
    label: "Lobsters",
    emoji: "🦞",
    badge: "border-red-500/30 bg-red-500/10 text-red-700",
  },
};

/** 篩選器選項用的來源順序（不含「全部」，由呼叫端自行補）。 */
export const SOURCE_ORDER = [
  "hackernews",
  "devto",
  "threads",
  "ptt",
  "lobsters",
] as const satisfies readonly SourceLabel[];

/**
 * 把任意來源字串（含未知 / 舊字串）對應到來源中介資料；
 * 對不上就兜底成中性樣式並沿用原字串當 label，絕不回傳 undefined。
 */
export function sourceMeta(source: string): SourceMeta {
  return SOURCE_META[source as SourceLabel] ?? { ...NEUTRAL, label: source || NEUTRAL.label };
}
