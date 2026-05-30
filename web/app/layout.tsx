import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "Pulse · AI 工程師的每日情報秘書",
  description: "把 Reddit 與 HackerNews 的 AI 討論轉成結構化、可查詢、可訂閱的決策訊號。",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-TW" className={`dark ${inter.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-bg font-sans text-white antialiased selection:bg-accent-primary/30">
        {children}
      </body>
    </html>
  );
}
