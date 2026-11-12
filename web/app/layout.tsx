import type { Metadata, Viewport } from "next";
import "./globals.css";

const SITE = "https://yukkki305.github.io/subways/";

/**
 * 首屏前把主题写进 <html data-theme>：否则深色用户会看到一闪而过的浅色。
 * 必须内联、必须在 <head> 里、必须在样式表生效前执行；逻辑与 lib/theme.ts 的
 * resolveTheme 保持一致（存的是模式，不是解析结果）。
 *
 * 另外把结果挂到 window.__THEME__：MapView 建 style 时要读它。
 * 只读 data-theme 不保险——hydrate 期间 React 可能先把属性抹掉再补回来，
 * 于是地图会先用浅色调色板建出来（实测 215 ms 时仍是 #F4F1EA）。
 */
const THEME_INIT = `(function(){try{var k="subways-theme";var m=localStorage.getItem(k);var dark=window.matchMedia("(prefers-color-scheme: dark)").matches;var t=(m==="light"||m==="dark")?m:(dark?"dark":"light");document.documentElement.dataset.theme=t;document.documentElement.style.colorScheme=t;window.__THEME__=t;}catch(e){}})();`;

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
  // 同一份页面服务两种配色：浏览器 UI（地址栏）按系统偏好取色，手动切换不改变它
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f4f2ee" },
    { media: "(prefers-color-scheme: dark)", color: "#1a1a18" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT }} />
      </head>
      <body>{children}</body>
    </html>
  );
}
