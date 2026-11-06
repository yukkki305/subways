import type { Metadata } from "next";
import { notFound } from "next/navigation";

import MapView from "@/components/MapView";
import { citySummary, countsText, publicCityCodes } from "@/lib/cities";

const SITE = "https://yukkki305.github.io/subways/";

type Props = { params: Promise<{ city: string }> };

/** 静态导出：只为确实有数据的城市生成页面（上海在 `/`，不在这里重复） */
export const dynamicParams = false;

export function generateStaticParams() {
  return publicCityCodes().map((city) => ({ city }));
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { city } = await params;
  const c = citySummary(city);
  const url = `${SITE}${c.code}/`;
  const desc = `${c.label}城市轨道交通 ${countsText(c)}的地理真实图：点车站可看线路、站序与换乘。个人作品集项目，数据来自 OpenStreetMap，快照 ${c.snapshot ?? "日期待补"}。`;
  return {
    title: `中国铁路图鉴 · ${c.label}`,
    description: desc,
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      siteName: `中国铁路图鉴 · ${c.label}`,
      locale: "zh_CN",
      url,
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

export default async function CityPage({ params }: Props) {
  const { city } = await params;
  if (!publicCityCodes().includes(city)) notFound();
  const c = citySummary(city);
  return (
    <main className="app-main">
      <MapView cityCode={c.code} cityLabel={c.label} center={c.center} zoom={c.zoom} />
    </main>
  );
}
