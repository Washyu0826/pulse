import { resolve } from "node:path";

import { defineConfig } from "vitest/config";

/**
 * 前端首批單元測試設定。
 * 只測「純邏輯」（lib 工具 + 抽出的元件邏輯），不需瀏覽器 → 用 node 環境，
 * 不引入 jsdom / react-testing-library，把新增 devDependency 控制到最小（只有 vitest）。
 */
export default defineConfig({
  test: {
    environment: "node",
    include: ["tests/**/*.test.ts"],
  },
  resolve: {
    alias: {
      // 對齊 tsconfig 的 "@/*" → 專案根。
      "@": resolve(__dirname, "."),
    },
  },
});
