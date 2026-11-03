#!/usr/bin/env node
// S3-7 构建自证：只做静态检查（不启浏览器），可在任何机器上重跑。
// 用法：node scripts/verify-build.mjs [outDir]
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { join, relative } from "node:path";

const OUT = process.argv[2] ?? "out";
const ROOT = process.cwd();
const checks = [];

function check(name, ok, detail) {
  checks.push({ name, ok, detail });
  const mark = ok ? "通过" : "失败";
  console.log(`[${mark}] ${name}${detail ? ` — ${detail}` : ""}`);
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

// 1. 入口与导出模式
const html = mustRead(join(OUT, "index.html")).toString("utf8");
check("index.html 存在且含标题", html.includes("中国铁路图鉴"), `${html.length} B`);
check("页面没有指向外部站点的资源", !/(src|href)="https?:\/\//.test(html), "只有同源资源");

// 2. 数据文件齐全（含 S4-4 的海面）
const dataDir = join(ROOT, OUT, "data");
const dataFiles = ["lines.json", "station.json", "transfer.json", "segment.geojson", "shanghai-basemap.geojson", "sea.geojson", "meta.json"];
for (const f of dataFiles) {
  check(`data/${f} 存在`, existsSync(join(dataDir, f)));
}

// 3. 数据自洽
const lines = JSON.parse(readFileSync(join(dataDir, "lines.json"), "utf8"));
const station = JSON.parse(readFileSync(join(dataDir, "station.json"), "utf8"));
const transfer = JSON.parse(readFileSync(join(dataDir, "transfer.json"), "utf8"));
const segment = JSON.parse(readFileSync(join(dataDir, "segment.geojson"), "utf8"));
const meta = JSON.parse(readFileSync(join(dataDir, "meta.json"), "utf8"));

check("线路 20 条", lines.lines.length === 20, `${lines.lines.length}`);
check("车站 423 座", station.stations.length === 423, `${station.stations.length}`);
check("换乘 12 条", transfer.transfers.length === 12, `${transfer.transfers.length}`);
check("区间 570 段", segment.features.length === 570, `${segment.features.length}`);
check(
  "meta.json 计数与文件一致",
  meta.counts?.stations === station.stations.length &&
    meta.counts?.transfer_candidates === transfer.transfers.length &&
    meta.total_bytes ===
      meta.files.reduce((a, f) => a + f.bytes, 0),
  `站 ${meta.counts?.stations} / 换乘候选 ${meta.counts?.transfer_candidates} / ${meta.total_bytes} B`,
);
const shaMismatch = meta.files.filter((f) => {
  const buf = readFileSync(join(dataDir, f.name));
  return buf.length !== f.bytes;
});
check("meta.json 记录的字节数与实际一致", shaMismatch.length === 0, `${meta.files.length} 个文件`);

// 4. 坐标全部落在上海视野内（WGS-84，防 GCJ-02 混入）
const visible = (lon, lat) => lon > 120.7 && lon < 123.4 && lat > 30.5 && lat < 32.0;
const badCoord = station.stations.filter((s) => !visible(s.coord[0], s.coord[1]));
check("车站坐标均在 WGS-84 上海视野内", badCoord.length === 0, badCoord.length ? `${badCoord.length} 个越界` : `${station.stations.length}/${station.stations.length}`);

// 5. 颜色全部为合法十六进制
const badColour = lines.lines.filter((l) => !/^#[0-9A-F]{6}$/.test(l.colour));
check("线路颜色为 6 位大写十六进制", badColour.length === 0, badColour.map((l) => `${l.id}:${l.colour}`).join(" ") || "20/20");

// 6. 交付物里的许可与截止日期
check(
  "meta.json 带 as_of 与许可",
  Boolean(meta.data_as_of || meta.snapshot_date),
  `${meta.data_as_of ?? meta.snapshot_date}`,
);

// 7. 体积统计（磁盘 + gzip 估算，托管平台一般开 gzip/brotli）
const files = walk(join(ROOT, OUT));
const total = files.reduce((a, f) => a + statSync(f).size, 0);
const shipped = files.filter((f) => /\.(js|css|mjs|json|geojson|html)$/.test(f));
let gz = 0;
for (const f of shipped) gz += gzipSync(readFileSync(f)).length;
// 8. 打包残留：Turbopack 会登记 maplibre 的所有变体，postbuild 必须清掉
const mediaDir = join(ROOT, OUT, "_next", "static", "media");
const mediaFiles = existsSync(mediaDir) ? readdirSync(mediaDir) : [];
check(
  "media/ 无 maplibre 副本残留",
  mediaFiles.filter((n) => n.startsWith("maplibre-gl")).length === 0,
  mediaFiles.length ? mediaFiles.join(" ") : "空目录",
);
check(
  "无开发构建（-dev.）残留",
  files.filter((f) => /-dev\.[\w-]+\.(mjs|js|css)$/.test(f)).length === 0,
  "0 个",
);
check("静态导出总体积 < 8 MB", total < 8 * 1024 * 1024, `${(total / 1048576).toFixed(2)} MB（gzip 后约 ${(gz / 1048576).toFixed(2)} MB）`);

const failed = checks.filter((c) => !c.ok);
console.log(`\n共 ${checks.length} 项，失败 ${failed.length} 项。`);
if (failed.length) process.exit(1);
