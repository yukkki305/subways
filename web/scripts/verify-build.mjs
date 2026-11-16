#!/usr/bin/env node
// 构建自证（P1a-6.5 多城矩阵；P1b-1.1 并行化）：只做静态检查（不启浏览器），可在任何机器上重跑。
//
// 用法：
//   node scripts/verify-build.mjs                        # 校验 out/ 里所有城市（默认）
//   node scripts/verify-build.mjs --city gz              # 只校验广州
//   node scripts/verify-build.mjs out --city cd          # 指定产物目录
//   node scripts/verify-build.mjs --concurrency=1        # 串行（排查时序问题 / 量基准）
//
// 全局项（入口页、同源、打包残留、总体积）跑一次；每城项（数据齐全、计数、坐标、颜色、
// 页面与元信息）并发跑 —— 54 城时每城要读 4 个 JSON + 1 个 HTML，串行会很慢。
//
// 输出顺序固定：先全局入口页，再按 wanted 顺序逐城，最后全局汇总项。并发只影响耗时，
// 不影响结果与顺序，diff 时仍然可比。
import { existsSync, readdirSync, statSync } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import { gzip } from "node:zlib";
import { promisify } from "node:util";
import { join } from "node:path";

import { listCityCodes, loadCity, parseCityArg, sceneBbox } from "./city.mjs";

const gzipAsync = promisify(gzip);

// 只支持 --concurrency=N 的等号写法：parseCityArg 会把非 -- 参数当产物目录，带空格的形式会被误认。
const rawArgs = process.argv.slice(2);
const concArg = rawArgs.find((a) => a.startsWith("--concurrency="));
const CONCURRENCY = Math.max(1, Number(concArg?.split("=")[1] ?? 8) || 8);
const parsed = parseCityArg(concArg ? rawArgs.filter((a) => a !== concArg) : rawArgs);
const OUT = parsed.rest.find((a) => !a.startsWith("--")) ?? "out";
const ROOT = process.cwd();
const OUT_ABS = join(ROOT, OUT);

/** 一次运行的全部断言，按最终输出顺序追加 */
const checks = [];

// 体积上限：P1b 全量 54 城，按 4 城实测线性外推约 70–85 MB。
// 依据、测算表与备选方案见 docs/decisions/0005-size-budget.md（2026-11-16 修订）。
const SIZE_LIMIT_MB = 80;
// 单城数据上限：总量卡不住「某一城爆炸」——平均值会把它稀释掉
const CITY_DATA_LIMIT_MB = 5;

function report(list) {
  for (const c of list) console.log(`[${c.ok ? "通过" : "失败"}] ${c.name}${c.detail ? ` — ${c.detail}` : ""}`);
}

/** 有界并发：limit 条 worker 从队列里取任务，结果按输入顺序回填 */
async function pool(items, limit, worker) {
  const results = new Array(items.length);
  let next = 0;
  const runners = Array.from({ length: Math.min(limit, items.length) }, async () => {
    for (;;) {
      const i = next++;
      if (i >= items.length) return;
      results[i] = await worker(items[i], i);
    }
  });
  await Promise.all(runners);
  return results;
}

async function readUtf8(abs) {
  return (await readFile(abs)).toString("utf8");
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

const started = Date.now();

// ── 全局：入口页 ──────────────────────────────────────────
const indexPath = join(ROOT, OUT, "index.html");
if (!existsSync(indexPath)) throw new Error(`缺少 ${join(OUT, "index.html")}（先跑 npm run build）`);
const html = await readUtf8(indexPath);
const entryChecks = [];
entryChecks.push({
  name: "index.html 存在且含标题",
  ok: html.includes("中国铁路图鉴"),
  detail: `${html.length} B`,
});

// ── 逐城（并发） ─────────────────────────────────────────
const wanted = parsed.explicit ? [parsed.city] : citiesInBuild();
if (wanted.length === 0) throw new Error(`out/data/ 下没有找到任何城市（先跑 npm run build）`);
const allCodes = listCityCodes();
const unknown = wanted.filter((c) => !allCodes.includes(c));
if (unknown.length) throw new Error(`未知城市：${unknown.join(", ")}（可用：${allCodes.join(", ")}）`);

// cities.json：六个字段都要对得上，否则城市切换器会显示错数字
const citiesJsonPath = join(OUT_ABS, "data", "cities.json");
const citiesJson = existsSync(citiesJsonPath) ? JSON.parse(await readUtf8(citiesJsonPath)) : [];

const CORE_FILES = ["lines.json", "station.json", "transfer.json", "segment.geojson"];

/** 一座城的 21 项；返回自己的断言数组（顺序即打印顺序） */
async function cityChecks(code) {
  const found = [];
  const add = (name, ok, detail) => found.push({ name, ok, detail });

  const cfg = loadCity(code);
  const dataDir = join(OUT_ABS, "data", code);
  const metaPath = join(dataDir, "meta.json");
  if (!existsSync(metaPath)) throw new Error(`缺少 out/data/${code}/meta.json（先跑 npm run build，prebuild 会同步数据）`);
  const meta = JSON.parse(await readUtf8(metaPath));
  const label = meta.city_label ?? cfg.name;
  const seen = (n) => `[${code}] ${n}`;

  // 1) 页面存在且带城市名
  const page = pagePath(code);
  const pageAbs = join(OUT_ABS, page);
  const pageHtml = existsSync(pageAbs) ? await readUtf8(pageAbs) : "";
  add(
    seen(`${page} 存在且含「${label}」`),
    Boolean(pageHtml) && pageHtml.includes(label),
    pageHtml ? `${pageHtml.length} B` : "缺失",
  );
  add(seen("页面资源全部同源"), pageHtml ? externalOf(pageHtml).length === 0 : true, "外链仅限元信息");

  // 2) 数据文件齐全（核心四件 + meta 登记项）
  for (const f of CORE_FILES) add(seen(`data/${code}/${f} 存在`), existsSync(join(dataDir, f)));
  add(seen("meta.json 的城市与本次校验一致"), meta.city_code === cfg.code, `${meta.city_code} / ${label}`);
  for (const f of meta.files ?? []) {
    add(seen(`data/${code}/${f.name} 存在（meta 登记）`), existsSync(join(dataDir, f.name)));
  }

  // 3) 数据自洽
  const [lines, station, transfer, segment] = await Promise.all([
    readUtf8(join(dataDir, "lines.json")).then(JSON.parse),
    readUtf8(join(dataDir, "station.json")).then(JSON.parse),
    readUtf8(join(dataDir, "transfer.json")).then(JSON.parse),
    readUtf8(join(dataDir, "segment.geojson")).then(JSON.parse),
  ]);

  add(seen(`线路 ${cfg.line_count_expected} 条（城市配置）`), lines.lines.length === cfg.line_count_expected, `${lines.lines.length}`);
  const lineIds = new Set(lines.lines.map((l) => l.id));
  const missingIds = cfg.line_ids.filter((id) => !lineIds.has(id));
  const extraIds = [...lineIds].filter((id) => !cfg.line_ids.includes(id));
  add(
    seen("线路 id 与城市配置一致"),
    missingIds.length === 0 && extraIds.length === 0,
    missingIds.length || extraIds.length
      ? `缺 ${missingIds.slice(0, 3).join(",") || "-"} / 多 ${extraIds.slice(0, 3).join(",") || "-"}`
      : `${lineIds.size} 个`,
  );
  add(
    seen("meta.json 计数与文件一致"),
    meta.counts?.stations === station.stations.length &&
      meta.counts?.lines === lines.lines.length &&
      meta.counts?.transfers === transfer.transfers.length &&
      meta.counts?.segments === segment.features.length &&
      meta.total_bytes === meta.files.reduce((a, f) => a + f.bytes, 0),
    `线路 ${meta.counts?.lines} / 站 ${meta.counts?.stations} / 区间 ${meta.counts?.segments} / 换乘 ${meta.counts?.transfers} / ${meta.total_bytes} B`,
  );
  // 字节数要逐个 stat：54 城时有 300+ 个文件，串行 stat 也要几秒，这里并发
  const sizes = await pool(meta.files ?? [], CONCURRENCY, async (f) => (await stat(join(dataDir, f.name))).size);
  add(
    seen("meta.json 记录的字节数与实际一致"),
    (meta.files ?? []).every((f, i) => sizes[i] === f.bytes),
    `${(meta.files ?? []).length} 个文件`,
  );
  // 单城数据量：总量 80 MB 是 54 城的平均值游戏，某一城爆到 8 MB 也能「通过」
  const cityBytes = sizes.reduce((a, n) => a + n, 0);
  add(
    seen(`单城数据 < ${CITY_DATA_LIMIT_MB} MB`),
    cityBytes < CITY_DATA_LIMIT_MB * 1024 * 1024,
    `${(cityBytes / 1048576).toFixed(2)} MB`,
  );

  // 4) 坐标全在该城视野内（WGS-84，防 GCJ-02 混入）
  const bb = sceneBbox(cfg);
  const visible = (lon, lat) => lon > bb.west && lon < bb.east && lat > bb.south && lat < bb.north;
  const badCoord = station.stations.filter((s) => !visible(s.coord[0], s.coord[1]));
  add(
    seen(`车站坐标均在 WGS-84 ${cfg.city}视野内`),
    badCoord.length === 0,
    badCoord.length
      ? `${badCoord.length} 个越界：${badCoord.slice(0, 2).map((s) => s.name).join(",")}`
      : `${station.stations.length}/${station.stations.length}`,
  );

  // 5) 颜色合法
  const badColour = lines.lines.filter((l) => !/^#[0-9A-F]{6}$/.test(l.colour));
  add(
    seen("线路颜色为 6 位大写十六进制"),
    badColour.length === 0,
    badColour.map((l) => `${l.id}:${l.colour}`).join(" ") || `${lines.lines.length}/${lines.lines.length}`,
  );

  // 6) 许可与截止日期
  add(seen("meta.json 带 as_of 与许可"), Boolean(meta.data_as_of || meta.snapshot_date), `${meta.data_as_of ?? meta.snapshot_date}`);

  // 7) cities.json 里的条目与 meta 一致（城市切换器读的就是它）
  const entry = citiesJson.find((c) => c.code === code);
  add(
    seen("cities.json 条目与 meta 一致"),
    Boolean(entry) &&
      entry.lines === meta.counts?.lines &&
      entry.stations === meta.counts?.stations &&
      entry.segments === meta.counts?.segments &&
      entry.transfers === meta.counts?.transfers,
    entry ? `${entry.lines}/${entry.stations}/${entry.segments}/${entry.transfers}` : "缺条目",
  );

  return found;
}

const perCity = await pool(wanted, CONCURRENCY, (code) => cityChecks(code));

// ── 全局汇总项 ────────────────────────────────────────────
const tail = [];
const addTail = (name, ok, detail) => tail.push({ name, ok, detail });

// cities.json 与「产物里实际存在的城市」必须双向一致：多一条会切到 404，少一条会漏城市
const inBuild = citiesInBuild();
addTail(
  "cities.json 覆盖产物里的全部城市",
  citiesJson.length === inBuild.length && citiesJson.every((c) => inBuild.includes(c.code)),
  `cities.json ${citiesJson.length} 条 / 产物 ${inBuild.length} 城`,
);

// sitemap 必须列全每一页
const sitemapPath = join(OUT_ABS, "sitemap.xml");
const sitemap = existsSync(sitemapPath) ? await readUtf8(sitemapPath) : "";
const sitemapUrls = [...sitemap.matchAll(/<loc>([^<]+)<\/loc>/g)].map((m) => m[1]);
addTail(
  "sitemap.xml 覆盖每个城市页",
  wanted.every((c) => sitemapUrls.some((u) => (c === "sh" ? /\/subways\/$/.test(u) : u.endsWith(`/subways/${c}/`)))),
  `${sitemapUrls.length} 条 URL`,
);
addTail("sitemap.xml 收录城市总览页", sitemapUrls.some((u) => /\/subways\/cities\/$/.test(u)), sitemapUrls.find((u) => u.endsWith("/cities/")) ?? "缺 /cities/");

// ── UX 阶段 3：总览页（每张卡片一张 SVG 轮廓） ─────────────
const citiesPage = join(OUT_ABS, "cities", "index.html");
const citiesHtml = existsSync(citiesPage) ? await readUtf8(citiesPage) : "";
addTail("out/cities/index.html 存在", citiesHtml.length > 0, citiesHtml ? `${(citiesHtml.length / 1024).toFixed(0)} KB` : "缺文件");
if (citiesHtml) {
  const labels = wanted.map((c) => loadCity(c).web?.city_label ?? loadCity(c).name);
  const missing = labels.filter((n) => !citiesHtml.includes(n));
  addTail("总览页列出每个城市的名字", missing.length === 0, missing.length ? `缺：${missing.join("、")}` : labels.join(" / "));
  const paths = (citiesHtml.match(/<path /g) ?? []).length;
  addTail("总览页缩略图有线路轮廓", paths > wanted.length, `${paths} 条 path（每城至少 1 条）`);
  // 卡片必须真的链到对应城市页：href 带 basePath，上海指根
  const hrefProblems = wanted.filter((c) => {
    const want = c === "sh" ? 'href="/subways/"' : `href="/subways/${c}/"`;
    return !citiesHtml.includes(want);
  });
  addTail(
    "总览页每张卡片链到对应城市页",
    hrefProblems.length === 0,
    hrefProblems.length ? `缺：${hrefProblems.join("、")}` : `${wanted.length} 条链接`,
  );

  // P1b-1.2：按省分组。54 城时一排 54 张卡片不可用，省分组标题必须和配置里的省份一一对应。
  const provinces = [...new Set(wanted.map((c) => loadCity(c).province).filter(Boolean))];
  const groupHeadings = (citiesHtml.match(/class="cities__group-title"/g) ?? []).length;
  const missingProvince = provinces.filter((p) => !citiesHtml.includes(`>${p}`));
  addTail(
    "总览页按省分组且省名齐全",
    groupHeadings === provinces.length && missingProvince.length === 0,
    missingProvince.length ? `缺：${missingProvince.join("、")}` : `${provinces.length} 组：${provinces.join(" / ")}`,
  );
}

// ── UX 阶段 4：主题两套值的唯一不变量 ─────────────────────
// 界面用 CSS 变量、地图用 lib/theme.ts；两边各有一份纸色，必须相等，否则
// 加载遮罩 / casing / 页脚会与地图底色不一致（肉眼是「一圈边」）。
// 这里直接读源码而不是构建产物：常量改错时构建本身不会报错，只有切主题才看得出来。
const [cssSrc, themeSrc] = await Promise.all([
  readUtf8(join(ROOT, "app", "globals.css")),
  readUtf8(join(ROOT, "lib", "theme.ts")),
]);

function cssVar(block, name) {
  const m = new RegExp(`${name}:\\s*(#[0-9a-fA-F]{3,8})`).exec(block);
  return m ? m[1].toLowerCase() : null;
}
function themeConst(name) {
  // 取 `export const LIGHT: Palette = { ... }` / DARK 里的 paper 字段
  const block = new RegExp(`const ${name}:\\s*Palette\\s*=\\s*\\{([\\s\\S]*?)\\n\\}`).exec(themeSrc);
  if (!block) return null;
  const m = /paper:\s*"(#[0-9a-fA-F]{3,8})"/.exec(block[1]);
  return m ? m[1].toLowerCase() : null;
}

// 注意：文件头的注释里也写了 `:root[data-theme="dark"]`，所以必须按「行首选择器」定位，
// 不能直接 indexOf 字符串（第一版就是这么错的：light 段被切在注释处，取不到 --c-paper）。
const darkIdx = cssSrc.search(/^:root\[data-theme="dark"\]\s*\{/m);
const lightRoot = darkIdx > 0 ? cssSrc.slice(0, darkIdx) : cssSrc;
const darkRoot = darkIdx > 0 ? cssSrc.slice(darkIdx) : "";
const pairs = [
  ["浅色 --c-paper", cssVar(lightRoot, "--c-paper"), themeConst("LIGHT")],
  ["深色 --c-paper", cssVar(darkRoot, "--c-paper"), themeConst("DARK")],
];
for (const [label, cssValue, themeValue] of pairs) {
  addTail(
    `${label} 与 lib/theme.ts 同值`,
    Boolean(cssValue) && cssValue === themeValue,
    cssValue && themeValue ? `${cssValue} / ${themeValue}` : `解析失败（css=${cssValue} theme=${themeValue}）`,
  );
}

// ── 全局：打包残留与体积 ──────────────────────────────────
const files = walk(OUT_ABS);
const total = files.reduce((a, f) => a + statSync(f).size, 0);
const shipped = files.filter((f) => /\.(js|css|mjs|json|geojson|html)$/.test(f));
// gzip 是这里唯一的重活（54 城时约 70 MB）：按并发压，别串行等
const gzParts = await pool(shipped, CONCURRENCY, async (f) => (await gzipAsync(await readFile(f))).length);
const gz = gzParts.reduce((a, n) => a + n, 0);

// 预警线（不判失败）：80 MB 是 54 城的硬线，按 4 城实测外推到 54 城正好落在 80 MB 附近，
// 所以在 90% 就先喊一声，避免最后几批才突然撞线（见 ADR 0005 修订节）。
const WARN_RATIO = 0.9;
if (total >= SIZE_LIMIT_MB * 1024 * 1024 * WARN_RATIO) {
  console.log(
    `\n[注意] 体积已到上限的 ${((total / (SIZE_LIMIT_MB * 1024 * 1024)) * 100).toFixed(0)}%` +
      `（${(total / 1048576).toFixed(1)} / ${SIZE_LIMIT_MB} MB）——加城前先看 ADR 0005 的备选方案。\n`,
  );
}

const mediaDir = join(OUT_ABS, "_next", "static", "media");
const mediaFiles = existsSync(mediaDir) ? readdirSync(mediaDir) : [];
addTail(
  "media/ 无 maplibre 副本残留",
  mediaFiles.filter((n) => n.startsWith("maplibre-gl")).length === 0,
  mediaFiles.length ? mediaFiles.join(" ") : "空目录",
);
addTail("无开发构建（-dev.）残留", files.filter((f) => /-dev\.[\w-]+\.(mjs|js|css)$/.test(f)).length === 0, "0 个");
addTail(
  `静态导出总体积 < ${SIZE_LIMIT_MB} MB`,
  total < SIZE_LIMIT_MB * 1024 * 1024,
  `${(total / 1048576).toFixed(2)} MB（gzip 后约 ${(gz / 1048576).toFixed(2)} MB）`,
);

// ── 输出：入口页 → 每城（按 wanted 顺序）→ 全局汇总 ──────
report(entryChecks);
for (const list of perCity) report(list);
report(tail);
checks.push(...entryChecks, ...perCity.flat(), ...tail);

const failed = checks.filter((c) => !c.ok);
const elapsed = ((Date.now() - started) / 1000).toFixed(2);
console.log(
  `\n共 ${checks.length} 项，失败 ${failed.length} 项（${wanted.length} 城：${wanted.join(" / ")}；并发 ${CONCURRENCY}；${elapsed} s）。`,
);
if (failed.length) process.exit(1);
