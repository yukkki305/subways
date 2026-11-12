import type { MetadataRoute } from "next";

import { HOME_CITY, citySummary, publicCityCodes } from "@/lib/cities";

/**
 * P1a-6.2：站点地图由城市清单生成，不再手写。
 *
 * GitHub Pages 是项目站点，站点根在 `/subways/` 下，所以 loc 必须带这个前缀。
 * lastModified 取该城数据快照日期（不是构建时间）——数据没变就不该告诉搜索引擎变了。
 */
const SITE = "https://yukkki305.github.io/subways/";

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const home = citySummary(HOME_CITY);
  const rest = publicCityCodes().map((code) => citySummary(code));
  // 总览页取各城里最新的快照日期：任何一城更新，它都该重新被抓取
  const newest = [home, ...rest]
    .map((c) => c.asOf)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(-1);

  return [
    {
      url: SITE,
      lastModified: home.asOf ?? undefined,
      changeFrequency: "monthly",
      priority: 1,
    },
    {
      url: `${SITE}cities/`,
      lastModified: newest,
      changeFrequency: "monthly",
      priority: 0.9,
    },
    ...rest.map((c) => ({
      url: `${SITE}${c.code}/`,
      lastModified: c.asOf ?? undefined,
      changeFrequency: "monthly" as const,
      priority: 0.8,
    })),
  ];
}
