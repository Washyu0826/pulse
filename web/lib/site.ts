/**
 * 站台層級設定（metadata / SEO / 分享卡共用）。
 * 部署網址走 NEXT_PUBLIC_SITE_URL；本機開發回退 localhost。
 */
export const SITE = {
  name: "Pulse",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  title: "Pulse · 每天的 AI 實用情報",
  description:
    "把技術社群與中文 Threads 的 AI 討論，整理成可查詢的「新工具 / 模型動態 / 用法 / 風險 / 倫理」情報。",
  tagline: "Daily AI intel, curated.",
  locale: "zh_TW",
  // 監測的模型 slug（sitemap / 導覽共用）。
  models: ["gpt", "claude", "gemini", "grok", "llama", "deepseek"] as const,
} as const;
