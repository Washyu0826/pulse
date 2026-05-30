import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Pulse 設計系統
        bg: {
          DEFAULT: "#0A0F1E",
          card: "#151B2D",
          cardLight: "#1E2438",
        },
        border: {
          DEFAULT: "#2A3149",
        },
        accent: {
          primary: "#8B5CF6",  // 紫
          cyan: "#06B6D4",     // 青
          pink: "#EC4899",     // 粉
        },
        sentiment: {
          positive: "#10B981",
          neutral: "#F59E0B",
          negative: "#EF4444",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
