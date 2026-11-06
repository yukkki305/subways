import type { Metadata } from "next";

import MapView from "@/components/MapView";
import { HOME_CITY, citySummary, countsText } from "@/lib/cities";

const SITE = "https://yukkki305.github.io/subways/";

/** 首页固定为上海（P1a-6.2：不再单独生成 `/sh/`，避免同一内容两份 URL） */
export function generateMetadata(): Metadata {
  const c = citySummary(HOME_CITY);
  const desc = `${c.label}城市轨道交通 ${countsText(c)}的地理真实图：点车站可看线路、站序与换乘。个人作品集项目，数据来自 OpenStreetMap，快照 ${c.snapshot ?? "日期待补"}。`;
  return {
    title: `中国铁路图鉴 · ${c.label}`,
    description: desc,
    alternates: { canonical: SITE },
    openGraph: {
      type: "website",
      siteName: `中国铁路图鉴 · ${c.label}`,
      locale: "zh_CN",
      url: SITE,
      title: `中国铁路图鉴 · ${c.label}`,
      description: desc,
      images: [{ url: `${SITE}og.jpg`, width: 1200, height: 630, alt: `${c.label}轨道交通线路地理走向图` }],
    },
    twitter: {
      card: "summary_large_image",
      title: `中国铁路图鉴 · ${c.label}`,
      description: desc,
      images: [`${SITE}og.jpg`],
    },
  };
}

export default function Page() {
  const c = citySummary(HOME_CITY);
  return (
    <main className="app-main">
      <MapView cityCode={c.code} cityLabel={c.label} center={c.center} zoom={c.zoom} />
    </main>
  );
}
