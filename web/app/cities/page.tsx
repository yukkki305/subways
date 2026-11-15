import type { Metadata } from "next";
import Link from "next/link";

import { HOME_CITY, cityGroups, countsText } from "@/lib/cities";
import { cityThumb } from "@/lib/thumbnails";

/**
 * UX 阶段 3（D1/D2）：城市总览页；P1b-1.2 改成按省分组。
 *
 * 放在 `/cities/` 而不是把 `/` 改成总览：`/` 是已经发出去的上海旗舰链接（README、
 * 简历、分享卡片都指向它），换成总览页会让老链接「打开不是那张图」。
 *
 * 缩略图在构建期用 segment.geojson 现算 SVG（lib/thumbnails.ts），不截图、不请求瓦片。
 * 分组不是为了现在好看（只有 4 城），而是 54 城时的唯一可用形态：一排 54 张卡片没法看。
 */
const SITE = "https://yukkki305.github.io/subways/";

export const metadata: Metadata = {
  title: "全部城市 · 中国铁路图鉴",
  description: "中国城市轨道交通线路总览，按省级行政区整理：线路数、车站数、区间与换乘，点进去看真实走向。",
  alternates: { canonical: `${SITE}cities/` },
  openGraph: {
    title: "全部城市 · 中国铁路图鉴",
    description: "按省整理的城市地铁网络总览，每张卡片都是真实几何的轮廓。",
    url: `${SITE}cities/`,
    images: [`${SITE}og.jpg`],
  },
};

function Thumb({ d, colour, type }: { d: string; colour: string; type: string }) {
  // 与地图同一套制式表达：磁浮虚线、APM 点线，其余实线。
  // 线宽 7：viewBox 1000 映射到 ~230 px 的卡片里约 1.6 px，再细就糊了。
  const dash = type === "maglev" ? "10 7" : type === "apm" ? "1 9" : undefined;
  return (
    <path
      d={d}
      fill="none"
      stroke={colour}
      strokeWidth={7}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={dash}
    />
  );
}

export default function CitiesPage() {
  const groups = cityGroups();
  const cards = groups.flatMap((g) => g.cities);

  const totalLines = cards.reduce((n, x) => n + x.lines, 0);
  const totalStations = cards.reduce((n, x) => n + (x.stations ?? 0), 0);

  return (
    <main className="cities">
      <header className="cities__head">
        <h1>中国铁路图鉴</h1>
        <p className="cities__lede">
          {cards.length} 座城市 · {groups.length} 个省级行政区 · {totalLines} 条线路 ·{" "}
          {totalStations.toLocaleString("zh-CN")} 站。每一张都是按真实走向画的，点开可以查线路、站序与换乘。
        </p>
      </header>

      {groups.map((group) => (
        <section className="cities__group" key={group.province}>
          <h2 className="cities__group-title">
            {group.province}
            <span className="cities__group-count">
              {group.cities.length} 城 · {group.cities.reduce((n, c) => n + c.lines, 0)} 条线路
            </span>
          </h2>
          <ul
            className="cities__grid"
            // 一城一组的省（现在几乎都是）只给一列宽：否则卡片右边留出三列空位，看着像坏图。
            // 上限 4 列 = 桌面端 1080px 栏宽下的自然列数。
            style={{ "--cols": Math.min(4, group.cities.length) } as React.CSSProperties}
          >
            {group.cities.map((c) => {
              const thumb = cityThumb(c.code);
              return (
                <li key={c.code}>
                  <Link className="city-card" href={c.href}>
                    <span className="city-card__thumb">
                      {thumb ? (
                        <svg viewBox="0 0 1000 700" role="img" aria-label={`${c.label}地铁网络轮廓`}>
                          {thumb.lines.map((l) => (
                            <Thumb key={l.id} d={l.d} colour={l.colour} type={l.type} />
                          ))}
                        </svg>
                      ) : (
                        <span className="city-card__nothumb">缩略图待生成</span>
                      )}
                    </span>
                    <span className="city-card__body">
                      <span className="city-card__name">{c.label}</span>
                      <span className="city-card__meta">{countsText(c)}</span>
                      <span className="city-card__sub">
                        {c.asOf ? `数据 ${c.asOf}` : "数据日期未知"}
                        {c.hasBasemap ? " · 含底图" : ""}
                        {c.code === HOME_CITY ? " · 首页" : ""}
                      </span>
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      ))}

      <footer className="cities__foot">
        <p>数据 © OpenStreetMap contributors（ODbL-1.0），个人作品集项目，数据仅供参考。</p>
        <p>
          <Link href="/">回到上海</Link>
        </p>
      </footer>
    </main>
  );
}
