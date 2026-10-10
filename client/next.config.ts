import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  // dev 模式放行 127.0.0.1：Next 16 dev 默认把非白名单来源视为跨源并阻断 /_next/hmr，
  // 会导致用 127.0.0.1 访问时页面永不 hydrate（表现为按钮恒禁用、卡骨架屏且无报错）
  allowedDevOrigins: ["127.0.0.1"],
  // 开发代理：/api 与 /socket.io → FastAPI 后端（D19 Nginx 接管统一入口）
  async rewrites() {
    const api = process.env.API_ORIGIN ?? "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/socket.io/:path*", destination: `${api}/socket.io/:path*` },
    ];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
