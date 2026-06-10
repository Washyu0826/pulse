import {
  AlertTriangle,
  BarChart3,
  CircleDashed,
  Scale,
  Sparkles,
  Wrench,
} from "lucide-react";
import type { ComponentType } from "react";

import type { ThemeLabel } from "@/lib/types";

/**
 * 五大實用主題（+ 低信心 fallback「其他」）的呈現順序與視覺（icon + 說明）——
 * hero / 主題分區 / 摘要列共用。與 ml/ml/theme.py THEME_HYPOTHESES 對齊（2026-06 改版：
 * 原 3 類 新工具/使用方法/邊界 → 5 類，「邊界」拆成 風險限制 + 倫理法規，並補 模型動態）。
 *
 * 設計系統刻意 2 色克制（冷墨 ink + 單一藍 accent），故各主題共用同一 accent，
 * 靠 icon 形狀區分（Manus 風）；icon 選用呼應後端 __main__ 的 emoji（🆕📊🛠️🚧⚖️⚪）。
 * 注意：class 字串需為字面量，Tailwind 才掃得到（勿動態拼接）。
 */
export const THEME_ORDER = [
  "新工具",
  "模型動態",
  "使用方法",
  "風險限制",
  "倫理法規",
] as const satisfies readonly ThemeLabel[];

/** 低信心 fallback 主題（與後端 OTHER_LABEL 一致）。 */
export const OTHER_THEME: ThemeLabel = "其他";

export interface ThemeMeta {
  Icon: ComponentType<{ className?: string }>;
  emoji: string; // 對應後端 __main__ 的 emoji，純文字場景可用
  blurb: string;
  text: string;
  bg: string;
  ring: string;
  bar: string;
}

// 2 色克制：各主題共用同一 accent（寶藍），靠 icon 形狀區分，不各自配色（Manus 風）。
const ACCENT = {
  text: "text-accent-primary",
  bg: "bg-accent-primary/10",
  ring: "ring-accent-primary/20",
  bar: "bg-accent-primary",
};

export const THEME_META: Record<ThemeLabel, ThemeMeta> = {
  新工具: { Icon: Sparkles, emoji: "🆕", blurb: "新發表的工具 / app / 產品 / 功能", ...ACCENT },
  模型動態: { Icon: BarChart3, emoji: "📊", blurb: "模型比較 / 評測 / 排名 / 價格 / 能力", ...ACCENT },
  使用方法: { Icon: Wrench, emoji: "🛠️", blurb: "提示技巧 / 教學 / 工作流 / use case", ...ACCENT },
  風險限制: { Icon: AlertTriangle, emoji: "🚧", blurb: "實務限制 / 失敗 / 幻覺 / 風險", ...ACCENT },
  倫理法規: { Icon: Scale, emoji: "⚖️", blurb: "倫理 / 法規 / 政策 / 隱私", ...ACCENT },
  其他: { Icon: CircleDashed, emoji: "⚪", blurb: "低信心 / 其他", ...ACCENT },
};

/**
 * 把任意主題字串（含未知 / 舊 3 類字串）對應到視覺中介資料；
 * 對不上就兜底成「其他」，絕不回傳 undefined（呼叫端不必再防 nullish）。
 */
export function themeMeta(theme: string): ThemeMeta {
  return THEME_META[theme as ThemeLabel] ?? THEME_META[OTHER_THEME];
}
