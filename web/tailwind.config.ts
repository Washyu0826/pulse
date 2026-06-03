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
          DEFAULT: "#FBF8EC",     // 淡黃紙底
          card: "#FFFEF9",        // 暖白卡
          cardLight: "#F5EFDB",   // hover 淡黃
        },
        border: {
          DEFAULT: "#EBE4CE",     // 暖黃淡邊
        },
        // 主要文字色（暖近黑）—— 取代原本的純白；用 text-ink/XX 控深淺。
        ink: {
          DEFAULT: "#26221C",
        },
        // 2 色克制：暖墨(ink) + 單一陶土 accent。cyan/pink 一律導向同色，
        // 確保任何殘留引用都不破壞「2 色」原則。
        accent: {
          primary: "#B5654A",  // 暖陶土（唯一彩色 accent）
          cyan: "#B5654A",
          pink: "#B5654A",
        },
        // sentiment 也收進 2 色：正面=陶土、其餘=暖墨深淺（不引入紅綠第三、四色）。
        sentiment: {
          positive: "#B5654A",
          neutral: "#9C9484",
          negative: "#6B6457",
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
