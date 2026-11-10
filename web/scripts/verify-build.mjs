#!/usr/bin/env node
// 构建自证（P1a-6.5 改成多城矩阵）：只做静态检查（不启浏览器），可在任何机器上重跑。
//
// 用法：
//   node scripts/verify-build.mjs                  # 校验 out/ 里所有城市（默认）
//   node scripts/verify-build.mjs --city gz        # 只校验广州
//   node scripts/verify-build.mjs out --city cd    # 指定产物目录
//
// 全局项（入口页、同源、打包残留、总体积）跑一次；每城项（数据齐全、计数、坐标、颜色、
// 页面与元信息）按城市循环。
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join } from "node:path";

import { listCityCodes, loadCity, parseCityArg, sceneBbox } from "./city.mjs";

const { city: cityArg, explicit: cityExplicit, rest: args } = parseCityArg(process.argv.slice(2));
const OUT = args.find((a) => !a.startsWith("--")) ?? "out";
const ROOT = process.cwd();
const OUT_ABS = join(ROOT, OUT);
const checks = [];

// 体积上限：P1a-6.4 之后四城 7.91 MB，原来的 8 MB（单城口径）已不代表用户成本。
// 依据与替代方案见 docs/decisions/0005-size-budget.md。
const SIZE_LIMIT_MB = 10;

function check(name, ok, detail) {
  checks.push({ name, ok, detail });
  console.log(`[${ok ? "通过" : "失败"}] ${name}${detail ? ` — ${detail}` : ""}`);
}

function mustRead(p) {
  const full = join(ROOT, p);
  if (!existsSync(full)) throw new Error(`缺少文件：${p}（先跑 npm run build）`);
  return readFileSync(full);
}

function walk(dir, acc = []) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else acc.push(p);
  }
  return acc;
}

/** 产物里实际有数据的城市（以 out/data/<code>/meta.json 为准） */
function citiesInBuild() {
  const dir = join(OUT_ABS, "data");
  if (!existsSync(dir)) return [];
  return readdirSync(dir, { withFileTypes: true })
    .filter((e) => e.isDirectory() && existsSync(join(dir, e.name, "meta.json")))
    .map((e) => e.name)
    .sort();
}

/** 城市页路径：上海在根，其余在 /<code>/ */
function pagePath(code) {
  return code === "sh" ? "index.html" : join(code, "index.html");
}

// ── 全局：入口页与资源同源 ────────────────────────────────
const html = mustRead(join(OUT, "index.html")).toString("utf8");
check("index.html 存在且含标题", html.includes("中国铁路图鉴"), `${html.length} B`);

const SITE_ORIGIN = "https://yukkki305.github.io/subways/";
const RESOURCE_RELS = /^(stylesheet|preload|modulepreload|icon|shortcut|apple-touch-icon|manifest)$/i;
function externalOf(indexHtml) {
  return [...indexHtml.matchAll(/<script[^>]+src="(https?:\/\/[^"]+)"/gi)]
    .map((m) => m[1])
    .concat([...indexHtml.matchAll(/<img[^>]+src="(https?:\/\/[^"]+)"/gi)].map((m) => m[1]))
    .concat(
      [...indexHtml.matchAll(/<link[^>]+>/gi)]
        .map((m) => m[0])
        .filter((tag) => RESOURCE_RELS.test((tag.match(/rel="([^"]+)"/i) ?? [])[1] ?? ""))
        .map((tag) => (tag.match(/href="(https?:\/\/[^"]+)"/i) ?? [])[1])
        .filter(Boolean),
    )
    .filter((u) => !u.startsWith(SITE_ORIGIN));
}

// ── 逐城 ─────────────────────────────────────────────────
const wanted = cityExplicit ? [cityArg] : citiesInBuild();
if (wanted.length === 0) throw new Error(`out/data/ 下没有找到任何城市（先跑 npm run build）`);
const allCodes = listCityCodes();
const unknown = wanted.filter((c) => !allCodes.includes(c));
if (unknown.length) throw new Error(`未知城市：${unknown.join(", ")}（可用：${allCodes.join(", ")}）`);

// cities.json：六个字段都要对得上，否则城市切换器会显示错数字
const citiesJsonPath = join(OUT_ABS, "data", "cities.json");
const citiesJson = existsSync(citiesJsonPath) ? JSON.parse(readFileSync(citiesJsonPath, "utf8")) : [];

for (const code of wanted) {
  const cfg = loadCity(code);
  const dataDir = join(OUT_ABS, "data", code);
  const metaPath = join(dataDir, "meta.json");
  if (!existsSync(metaPath)) throw new Error(`缺少 out/data/${code}/meta.json（先跑 npm run build，prebuild 会同步数据）`);
  const meta = JSON.parse(readFileSync(metaPath, "utf8"));
  const label = meta.city_label ?? cfg.name;
  const seen = (n) => `[${code}] ${n}`;

  // 1) 页面存在且带城市名
  const page = pagePath(code);
  const pageAbs = join(OUT_ABS, page);
  const pageHtml = existsSync(pageAbs) ? readFileSync(pageAbs, "utf8") : "";
  check(
    seen(`${page} 存在且含「${label}」`),
    Boolean(pageHtml) && pageHtml.includes(label),
    pageHtml ? `${pageHtml.length} B` : "缺失",
  );
  check(seen("页面资源全部同源"), pageHtml ? externalOf(pageHtml).length === 0 : true, "外链仅限元信息");

  // 2) 数据文件齐全（核心四件 + meta 登记项）
  const CORE_FILES = ["lines.json", "station.json", "transfer.json", "segment.geojson"];
  for (const f of CORE_FILES) check(seen(`data/${code}/${f} 存在`), existsSync(join(dataDir, f)));
  check(seen("meta.json 的城市与本次校验一致"), meta.city_code === cfg.code, `${meta.city_code} / ${label}`);
  for (const f of meta.files ?? []) {
    check(seen(`data/${code}/${f.name} 存在（meta 登记）`), existsSync(join(dataDir, f.name)));
  }

  // 3) 数据自洽
  const lines = JSON.parse(readFileSync(join(dataDir, "lines.json"), "utf8"));
  const station = JSON.parse(readFileSync(join(dataDir, "station.json"), "utf8"));
  const transfer = JSON.parse(readFileSync(join(dataDir, "transfer.json"), "utf8"));
  const segment = JSON.parse(readFileSync(join(dataDir, "segment.geojson"), "utf8"));

  check(
    seen(`线路 ${cfg.line_count_expected} 条（城市配置）`),
    lines.lines.length === cfg.line_count_expected,
    `${lines.lines.length}`,
  );
  const lineIds = new Set(lines.lines.map((l) => l.id));
  const missingIds = cfg.line_ids.filter((id) => !lineIds.has(id));
  const extraIds = [...lineIds].filter((id) => !cfg.line_ids.includes(id));
  check(
    seen("线路 id 与城市配置一致"),
    missingIds.length === 0 && extraIds.length === 0,
    missingIds.length || extraIds.length
      ? `缺 ${missingIds.slice(0, 3).join(",") || "-"} / 多 ${extraIds.slice(0, 3).join(",") || "-"}`
      : `${lineIds.size} 个`,
  );
  check(
    seen("meta.json 计数与文件一致"),
    meta.counts?.stations === station.stations.length &&
      meta.counts?.lines === lines.lines.length &&
      meta.counts?.transfers === transfer.transfers.length &&
      meta.counts?.segments === segment.features.length &&
      meta.total_bytes === meta.files.reduce((a, f) => a + f.bytes, 0),
    `线路 ${meta.counts?.lines} / 站 ${meta.counts?.stations} / 区间 ${meta.counts?.segments} / 换乘 ${meta.counts?.transfers} / ${meta.total_bytes} B`,
  );
  check(
    seen("meta.json 记录的字节数与实际一致"),
    meta.files.every((f) => readFileSync(join(dataDir, f.name)).length === f.bytes),
    `${meta.files.length} 个文件`,
  );

  // 4) 坐标全在该城视野内（WGS-84，防 GCJ-02 混入）
  const bb = sceneBbox(cfg);
  const visible = (lon, lat) => lon > bb.west && lon < bb.east && lat > bb.south && lat < bb.north;
  const badCoord = station.stations.filter((s) => !visible(s.coord[0], s.coord[1]));
  check(
    seen(`车站坐标均在 WGS-84 ${cfg.city}视野内`),
    badCoord.length === 0,
    badCoord.length ? `${badCoord.length} 个越界：${badCoord.slice(0, 2).map((s) => s.name).join(",")}` : `${station.stations.length}/${station.stations.length}`,
  );

  // 5) 颜色合法
  const badColour = lines.lines.filter((l) => !/^#[0-9A-F]{6}$/.test(l.colour));
  check(seen("线路颜色为 6 位大写十六进制"), badColour.length === 0, badColour.map((l) => `${l.id}:${l.colour}`).join(" ") || `${lines.lines.length}/${lines.lines.length}`);

  // 6) 许可与截止日期
  check(seen("meta.json 带 as_of 与许可"), Boolean(meta.data_as_of || meta.snapshot_date), `${meta.data_as_of ?? meta.snapshot_date}`);

  // 7) cities.json 里的条目与 meta 一致（城市切换器读的就是它）
  const entry = citiesJson.find((c) => c.code === code);
  check(
    seen("cities.json 条目与 meta 一致"),
    Boolean(entry) &&
      entry.lines === meta.counts?.lines &&
      entry.stations === meta.counts?.stations &&
      entry.segments === meta.counts?.segments &&
      entry.transfers === meta.counts?.transfers,
    entry ? `${entry.lines}/${entry.stations}/${entry.segments}/${entry.transfers}` : "缺条目",
  );
}

// cities.json 与「产物里实际存在的城市」必须双向一致：多一条会切到 404，少一条会漏城市
check(
  "cities.json 覆盖产物里的全部城市",
  citiesJson.length === citiesInBuild().length && citiesJson.every((c) => citiesInBuild().includes(c.code)),
  `cities.json ${citiesJson.length} 条 / 产物 ${citiesInBuild().length} 城`,
);

// sitemap 必须列全四页
const sitemapPath = join(OUT_ABS, "sitemap.xml");
const sitemap = existsSync(sitemapPath) ? readFileSync(sitemapPath, "utf8") : "";
const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
check(
  "sitemap.xml 覆盖每个城市页",
  wanted.every((c) => sitemapUrls.some((u) => (c === "sh" ? /\/subways\/$/.test(u) : u.endsWith(`/subways/${c}/`)))),
  `${sitemapUrls.length} 条 URL`,
);

// ── 全局：打包残留与体积 ──────────────────────────────────
const files = walk(OUT_ABS);
const total = files.reduce((a, f) => a + statSync(f).size, 0);
const shipped = files.filter((f) => /\.(js|css|mjs|json|geojson|html)$/.test(f));
let gz = 0;
for (const f of shipped) gz += gzipSync(readFileSync(f)).length;

const mediaDir = join(OUT_ABS, "_next", "static", "media");
const mediaFiles = existsSync(mediaDir) ? readdirSync(mediaDir) : [];
check(
  "media/ 无 maplibre 副本残留",
  mediaFiles.filter((n) => n.startsWith("maplibre-gl")).length === 0,
  mediaFiles.length ? mediaFiles.join(" ") : "空目录",
);
check("无开发构建（-dev.）残留", files.filter((f) => /-dev\.[\w-]+\.(mjs|js|css)$/.test(f)).length === 0, "0 个");
check(
  `静态导出总体积 < ${SIZE_LIMIT_MB} MB`,
  total < SIZE_LIMIT_MB * 1024 * 1024,
  `${(total / 1048576).toFixed(2)} MB（gzip 后约 ${(gz / 1048576).toFixed(2)} MB）`,
);

const failed = checks.filter((c) => !c.ok);
console.log(`\n共 ${checks.length} 项，失败 ${failed.length} 项（${wanted.length} 城：${wanted.join(" / ")}）。`);
if (failed.length) process.exit(1);
