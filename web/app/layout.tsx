import type { Metadata, Viewport } from "next";
import localFont from "next/font/local";
import "./globals.css";

import { SITE } from "@/lib/site";

// 字型自託管（woff2 bundle 進 repo）→ build 不連 Google Fonts，本機（TLS 攔截）與雲端都離線可建、無字型抖動。
// 變數軸版本（單檔涵蓋整個字重範圍）。CSS 變數名沿用 → 其餘樣式（tailwind var(--font-sans)）不變。
const inter = localFont({
  src: "./fonts/inter-latin-wght-normal.woff2",
  variable: "--font-sans",
  display: "swap",
  weight: "100 900",
});
const mono = localFont({
  src: "./fonts/jetbrains-mono-latin-wght-normal.woff2",
  variable: "--font-mono",
  display: "swap",
  weight: "100 800",
});
// 歐美書寫體（優雅手寫）：用於 wordmark；中文無對應字形會回退無襯線（見 tailwind script 字族）。
const script = localFont({
  src: "./fonts/dancing-script-latin-wght-normal.woff2",
  variable: "--font-script",
  display: "swap",
  weight: "400 700",
});

export const metadata: Metadata = {
  metadataBase: new URL(SITE.url),
  title: { default: SITE.title, template: "%s · Pulse" },
  description: SITE.description,
  applicationName: SITE.name,
  keywords: ["AI", "情報", "Threads", "LLM", "GPT", "Claude", "Gemini", "新工具", "模型動態", "AI 風險", "AI 倫理"],
  authors: [{ name: SITE.name }],
  openGraph: {
    type: "website",
    locale: SITE.locale,
    url: SITE.url,
    siteName: SITE.name,
    title: SITE.title,
    description: SITE.description,
  },
  twitter: {
    card: "summary_large_image",
    title: SITE.title,
    description: SITE.description,
  },
  robots: { index: true, follow: true },
  alternates: { canonical: "/" },
};

export const viewport: Viewport = {
  themeColor: "#4D74EA",
  colorScheme: "light",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW" className={`${inter.variable} ${mono.variable} ${script.variable}`}>
      <body className="min-h-screen bg-bg font-sans text-ink antialiased selection:bg-accent-primary/20">
        {children}
      </body>
    </html>
  );
}
