import type { Metadata } from "next";
import { Dancing_Script, Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });
// 歐美書寫體（優雅手寫）：用於 wordmark；中文無對應字形會回退無襯線。
const script = Dancing_Script({ subsets: ["latin"], variable: "--font-script", display: "swap", weight: ["600", "700"] });

export const metadata: Metadata = {
  title: "Pulse · 每天的 AI 實用情報",
  description: "把技術社群與中文 Threads 的 AI 討論，整理成可查詢的「新工具 / 用法 / 邊界」情報。",
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
