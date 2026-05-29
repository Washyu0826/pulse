import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Pulse · AI 工程師的每日情報秘書",
  description: "把 Reddit 與 HackerNews 的 AI 討論轉成結構化、可查詢、可訂閱的決策訊號。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-TW" className="dark">
      <body className="bg-bg text-white antialiased">
        {children}
      </body>
    </html>
  );
}
