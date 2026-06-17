/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Docker 部署：產出自含的 standalone server（.next/standalone 內含最小化 node_modules），
  // 讓最終 image 不必帶整包 node_modules，體積小且非 root 可跑。見 web/Dockerfile。
  output: "standalone",
  experimental: {
    // Server Actions 預設開啟（Next.js 14+）
  },
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8010",
  },
};

module.exports = nextConfig;
