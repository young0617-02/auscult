import { defineConfig } from "vitest/config";
import path from "node:path";

/** 单测配置：@/ 别名对齐 tsconfig；jsdom 环境供 localStorage/window 模拟 */
export default defineConfig({
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.ts"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
});
