import type { NextConfig } from "next";

/**
 * 静态导出：数据全部是构建期准备好的静态文件，页面不需要服务端。
 * 见 AGENTS.md 第 3 节「入库方式」与第 7 节目录约定。
 */
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  typedRoutes: false,
};

export default nextConfig;
