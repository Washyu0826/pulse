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
        // Pulse 設計系統 —— Manus 風暖色淺底（warm paper light theme）。
        bg: {
          DEFAULT: "#F4F7FC",     // 冷調淺藍白紙底
          card: "#FFFFFF",        // 乾淨白卡
          cardLight: "#EAF1FB",   // hover 淺藍
        },
        border: {
          DEFAULT: "#D9E2F1",     // 冷藍淡邊
        },
        // 主要文字色（冷調深岩藍）—— 用 text-ink/XX 控深淺。
        ink: {
          DEFAULT: "#1B2536",
        },
        // 2 色克制：冷墨(ink) + 單一藍 accent。cyan/pink 一律導向同色。
        accent: {
          primary: "#2E86FF",  // 亮藍（唯一彩色 accent）
          cyan: "#2E86FF",
          pink: "#2E86FF",
        },
        // sentiment 也收進 2 色：正面=亮藍、其餘=冷灰深淺（不引入紅綠第三、四色）。
        sentiment: {
          positive: "#2E86FF",
          neutral: "#8A97AC",
          negative: "#5A6677",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "-apple-system", "PingFang TC", "Microsoft JhengHei", "Noto Sans TC", "sans-serif"],
        mono: ["var(--font-mono)", "Consolas", "ui-monospace", "monospace"],
        // 優雅書寫體：部署用 Dancing Script；本機（TLS 抓不到 Google 字型）回退 Windows 優雅手寫體
        // （Gabriola 為 Windows 內建書法體，最優雅）。
        script: ["var(--font-script)", "Gabriola", "Segoe Script", "Palatino Linotype", "cursive"],
      },
    },
  },
  plugins: [],
};

export default config;
