/**
 * 站台層級設定（metadata / SEO / 分享卡共用）。
 * 部署網址走 NEXT_PUBLIC_SITE_URL；本機開發回退 localhost。
 */

/**
 * 監測的 6 個模型 —— 單一事實來源。
 * sitemap（slug）、決策頁（slug+name）、首頁篩選列（value+label）皆從此衍生，
 * 新增/調整模型只改這裡一處。
 */
export const MODELS = [
  { slug: "gpt", name: "GPT" },
  { slug: "claude", name: "Claude" },
  { slug: "gemini", name: "Gemini" },
  { slug: "grok", name: "Grok" },
  { slug: "llama", name: "Llama" },
  { slug: "deepseek", name: "DeepSeek" },
] as const;

export type ModelSlug = (typeof MODELS)[number]["slug"];

export const SITE = {
  name: "Pulse",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  title: "Pulse · 每天的 AI 實用情報",
  description:
    "把技術社群與中文 Threads 的 AI 討論，整理成可查詢的「新工具 / 模型動態 / 用法 / 風險 / 倫理」情報。",
  tagline: "Daily AI intel, curated.",
  locale: "zh_TW",
  // 監測的模型 slug（sitemap / 導覽共用）—— 衍生自 MODELS 單一來源。
  models: MODELS.map((m) => m.slug),
} as const;
