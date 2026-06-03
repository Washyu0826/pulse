import { AlertTriangle, Sparkles, Wrench } from "lucide-react";
import type { ComponentType } from "react";

/**
 * 三大實用主題的呈現順序與視覺（色彩編碼 + icon + 說明）—— hero / 三分區 / 摘要列共用。
 * 顏色用既有 token：新工具=青、使用方法=紫、邊界=琥珀（警示感）。
 * 注意：class 字串需為字面量，Tailwind 才掃得到（勿動態拼接）。
 */
export const THEME_ORDER = ["新工具", "使用方法", "邊界"] as const;

export interface ThemeMeta {
  Icon: ComponentType<{ className?: string }>;
  blurb: string;
  text: string;
  bg: string;
  ring: string;
  bar: string;
}

export const THEME_META: Record<string, ThemeMeta> = {
  新工具: {
    Icon: Sparkles,
    blurb: "新發表的工具 / 模型 / 產品",
    text: "text-accent-cyan",
    bg: "bg-accent-cyan/10",
    ring: "ring-accent-cyan/25",
    bar: "bg-accent-cyan",
  },
  使用方法: {
    Icon: Wrench,
    blurb: "提示技巧 / 教學 / 工作流",
    text: "text-accent-primary",
    bg: "bg-accent-primary/10",
    ring: "ring-accent-primary/25",
    bar: "bg-accent-primary",
  },
  邊界: {
    Icon: AlertTriangle,
    blurb: "限制 / 風險 / 要注意的坑",
    text: "text-sentiment-neutral",
    bg: "bg-sentiment-neutral/10",
    ring: "ring-sentiment-neutral/25",
    bar: "bg-sentiment-neutral",
  },
};
