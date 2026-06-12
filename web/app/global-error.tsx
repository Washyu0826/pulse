"use client";

/**
 * 全域錯誤邊界（root layout 自身崩潰時的最後防線）。
 * 會「取代」整個 root layout，所以必須自帶 <html>/<body>。
 * 刻意用 inline style（不依賴 Tailwind/globals 是否載入）確保任何情況下都看得到友善訊息。
 */
import { useEffect } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("[global-error]", error);
  }, [error]);

  return (
    <html lang="zh-TW">
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#F4F7FC",
          color: "#1B2536",
          fontFamily:
            "system-ui, -apple-system, 'PingFang TC', 'Microsoft JhengHei', 'Noto Sans TC', sans-serif",
        }}
      >
        <div style={{ maxWidth: 420, padding: "0 24px", textAlign: "center" }}>
          <div style={{ fontSize: 32 }}>⚠️</div>
          <h1 style={{ fontSize: 18, fontWeight: 600, marginTop: 16 }}>頁面發生未預期的錯誤</h1>
          <p style={{ fontSize: 14, lineHeight: 1.6, color: "rgba(27,37,54,0.6)", marginTop: 8 }}>
            我們已記錄這個問題。請重新整理，或稍後再試。
          </p>
          <button
            onClick={reset}
            style={{
              marginTop: 24,
              padding: "8px 18px",
              fontSize: 14,
              fontWeight: 500,
              color: "#fff",
              background: "#4D74EA",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
            }}
          >
            重新載入
          </button>
        </div>
      </body>
    </html>
  );
}
