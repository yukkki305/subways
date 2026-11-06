import type { Metadata, Viewport } from "next";
import "./globals.css";

const SITE = "https://yukkki305.github.io/subways/";

/**
 * P1a-6.2：页面级元信息（标题/描述/canonical/OG）改由各城市页面自己给，
 * 这里只留全站共用部分——默认标题、作者、关键词、robots。
 */
export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: { default: "中国铁路图鉴", template: "%s" },
  applicationName: "中国铁路图鉴",
  authors: [{ name: "yukkki305", url: "https://github.com/yukkki305" }],
  keywords: ["地铁地图", "城市轨道交通", "中国地铁", "MapLibre", "OpenStreetMap", "数据可视化", "作品集"],
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f4f2ee",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
