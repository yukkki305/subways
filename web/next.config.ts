import type { NextConfig } from "next";

/**
 * 静态导出：数据全部是构建期准备好的静态文件，页面不需要服务端。
 * 见 AGENTS.md 第 3 节「入库方式」与第 7 节目录约定。
 *
 * S6-1：发布目标是 GitHub Pages 的**项目站点**
 * `https://<owner>.github.io/<repo>/`，因此站点挂在 `/subways` 子路径下。
 * 页面内的绝对路径（`/_next/...`、`/data/...`、`/vendor/...`）必须带此前缀，
 * 否则线上全部 404。`NEXT_PUBLIC_BASE_PATH` 供客户端代码拼接运行时请求。
 */
const BASE_PATH = "/subways";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  typedRoutes: false,
  basePath: BASE_PATH,
  env: { NEXT_PUBLIC_BASE_PATH: BASE_PATH },
};

export default nextConfig;
