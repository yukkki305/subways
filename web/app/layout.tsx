import type { Metadata, Viewport } from "next";
import "./globals.css";

const SITE = "https://yukkki305.github.io/subways/";
const DESC =
  "上海 20 条城市轨道交通线路的地理真实图：423 座车站、570 个区间、12 条换乘，可点站看线路与站序。个人作品集项目，数据来自 OpenStreetMap。";

export const metadata: Metadata = {
  metadataBase: new URL(SITE),
  title: "中国铁路图鉴 · 上海",
  description: DESC,
  applicationName: "中国铁路图鉴",
  authors: [{ name: "yukkki305", url: "https://github.com/yukkki305" }],
  keywords: ["上海地铁", "城市轨道交通", "地铁地图", "MapLibre", "OpenStreetMap", "数据可视化", "作品集"],
  alternates: { canonical: SITE },
  openGraph: {
    type: "website",
    siteName: "中国铁路图鉴 · 上海",
    locale: "zh_CN",
    url: SITE,
    title: "中国铁路图鉴 · 上海",
    description: DESC,
    images: [{ url: "og.jpg", width: 1200, height: 630, alt: "上海轨道交通线路地理走向图" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "中国铁路图鉴 · 上海",
    description: DESC,
    images: ["og.jpg"],
  },
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
