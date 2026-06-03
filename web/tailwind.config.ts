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
          DEFAULT: "#FAF8F3",     // 暖米白紙底
          card: "#FFFFFF",        // 乾淨白卡
          cardLight: "#F4F1EA",   // hover 暖灰
        },
        border: {
          DEFAULT: "#E6E1D6",     // 暖砂淡邊
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
        // 部署/正常網路用 Caveat；本機（TLS 攔截抓不到 Google 字型）回退 Windows 系統手寫體。
        script: ["var(--font-script)", "Ink Free", "Segoe Script", "Brush Script MT", "Bradley Hand", "cursive"],
      },
    },
  },
  plugins: [],
};

export default config;
