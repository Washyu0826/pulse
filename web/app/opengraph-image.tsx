import { ImageResponse } from "next/og";

import { SITE } from "@/lib/site";

/**
 * 社群分享卡（OG / Twitter）。Next 自動把本檔當首頁的 opengraph-image。
 * 刻意只用拉丁文字（next/og 內建字型不含 CJK，放中文會變豆腐字），
 * 以品牌色 + 脈搏 mark 呈現，1200×630。
 */
// edge runtime：避開 @vercel/og 在 Node/Windows 下載入內建字型時的 fileURLToPath bug。
export const runtime = "edge";
export const alt = "Pulse — Daily AI intel, curated.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          padding: "0 96px",
          background: "#F4F7FC",
          color: "#1B2536",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
          <div
            style={{
              width: 96,
              height: 96,
              borderRadius: 24,
              background: "#4D74EA",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <svg width="60" height="60" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round">
              <path d="M1 12 H6 L8.5 5 L12.5 19 L15 12 H23" />
            </svg>
          </div>
          <div style={{ fontSize: 104, fontWeight: 800, letterSpacing: -2 }}>Pulse</div>
        </div>
        <div style={{ marginTop: 40, fontSize: 46, fontWeight: 600, color: "#1B2536" }}>
          {SITE.tagline}
        </div>
        <div style={{ marginTop: 20, fontSize: 30, color: "#4D74EA", fontWeight: 600 }}>
          Tools · Models · How-to · Risks · Ethics
        </div>
      </div>
    ),
    { ...size },
  );
}
