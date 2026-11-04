/**
 * 把数据管道的产物复制到 web/public/data/，并写一份 meta.json 供前端显示数据版本。
 *
 * 为什么复制而不是直接读 ../data/processed：
 *   Next.js 静态导出只会打包 public/ 与路由，仓库里的 data/ 在构建产物里不可见；
 *   而把 1.8 MB 数据 import 进 bundle 会让整包在数据更新时整体失效（见 web/README.md）。
 *
 * 用法：node scripts/sync-data.mjs [--city <code>] [--check]
 *   --city   城市 code（默认 sh，也可用环境变量 SUBWAY_WEB_CITY）
 *   --check  只比对、不写盘（CI/校验用）
 *
 * P1a-1.5：城市相关的东西（产物清单、路径、视野、城市名）全部来自
 * pipeline/cities/<code>.json，本脚本不再写死上海。
 */
import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { cityLabel, dataSources, listCityCodes, loadCity, parseCityArg, REPO } from "./city.mjs";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(__dirname, "..");
const PUBLIC = join(WEB, "public");
const OUT = join(PUBLIC, "data");
const VENDOR = join(PUBLIC, "vendor");

/**
 * 运行时静态资源。maplibre 的 render worker 经 Next 打包后 URL 会算错
 * （浏览器报 "Worker failed to load. Check that the worker URL is correct."），
 * 所以把 dist 里的 worker 原文件拷进 public/vendor，前端用 setWorkerUrl 指过去。
 * 该 worker 自包含（无 import），单文件即可。
 */
const VENDOR_FILES = [
  ["node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs", "maplibre-gl-worker.mjs"],
];

const { city, rest } = parseCityArg(process.argv.slice(2));
const checkOnly = rest.includes("--check");

async function sha256(path) {
  const buf = await readFile(path);
  return createHash("sha256").update(buf).digest("hex");
}

async function main() {
  let cfg;
  try {
    cfg = loadCity(city);
  } catch (err) {
    console.error(`[失败] ${err.message}`);
    console.error(`       可用城市：${listCityCodes().join(" / ")}`);
    process.exit(1);
  }

  await mkdir(OUT, { recursive: true });

  const entries = [];
  const problems = [];

  for (const { rel, name, optional } of dataSources(cfg)) {
    const src = join(REPO, rel);
    let st;
    try {
      st = await stat(src);
    } catch {
      if (!optional) problems.push(`缺少源文件：${rel}`);
      continue;
    }
    if (!st.isFile()) {
      if (!optional) problems.push(`不是文件：${rel}`);
      continue;
    }
    const dst = join(OUT, name);
    const hash = await sha256(src);
    let same = false;
    try {
      same = hash === (await sha256(dst));
    } catch {
      same = false;
    }
    if (!checkOnly && !same) {
      await copyFile(src, dst);
    }
    entries.push({
      name,
      source: relative(REPO, src).replaceAll("\\", "/"),
      bytes: st.size,
      sha256_16: hash.slice(0, 16),
      changed: !same,
    });
  }

  if (problems.length) {
    console.error(`[失败] 数据同步（${city}）：`);
    for (const p of problems) console.error("  - " + p);
    console.error(`       提示：先跑 python pipeline/run_city.py --city ${city}`);
    process.exit(1);
  }

  // 运行时静态资源（maplibre worker 等）
  await mkdir(VENDOR, { recursive: true });
  for (const [rel, name] of VENDOR_FILES) {
    const src = join(WEB, rel);
    const dst = join(VENDOR, name);
    let same = false;
    try {
      same = (await sha256(src)) === (await sha256(dst));
    } catch {
      same = false;
    }
    if (!checkOnly && !same) await copyFile(src, dst);
  }

  // 数据版本信息：前端用来显示「数据截止」，也方便排查前端看到的到底是哪一版
  const station = JSON.parse(await readFile(join(REPO, cfg.data_dir, "station.json"), "utf8"));
  const lines = JSON.parse(await readFile(join(REPO, cfg.data_dir, "lines.json"), "utf8"));
  const transfer = JSON.parse(await readFile(join(REPO, cfg.data_dir, "transfer.json"), "utf8"));
  const segment = JSON.parse(await readFile(join(REPO, cfg.data_dir, "segment.geojson"), "utf8"));
  const totalBytes = entries.reduce((n, e) => n + e.bytes, 0);
  const meta = {
    generated_at: new Date().toISOString(),
    city_code: cfg.code,
    city: cfg.name,
    city_label: cityLabel(cfg),
    snapshot_date: station.snapshot_date,
    data_as_of: station.as_of ?? station.snapshot_date,
    counts: {
      ...station.counts,
      lines: lines.lines.length,
      transfers: transfer.transfers.length,
      segments: segment.features.length,
    },
    total_bytes: totalBytes,
    files: entries.map(({ name, source, bytes, sha256_16 }) => ({ name, source, bytes, sha256_16 })),
  };
  if (!checkOnly) {
    await writeFile(join(OUT, "meta.json"), JSON.stringify(meta, null, 1) + "\n", "utf8");
  }

  const changed = entries.filter((e) => e.changed).map((e) => e.name);
  console.log(
    `${checkOnly ? "[检查] " : "[同步] "}${meta.city_label}（${cfg.code}）${entries.length} 个文件 → web/public/data/（${(totalBytes / 1024 / 1024).toFixed(2)} MB）`,
  );
  for (const e of entries) {
    console.log(`  ${e.changed ? "更新" : "一致"}  ${e.name.padEnd(26)} ${(e.bytes / 1024).toFixed(0).padStart(6)} KB  ${e.sha256_16}`);
  }
  console.log(
    `  快照 ${meta.snapshot_date}｜线路 ${meta.counts.lines}｜车站 ${meta.counts.stations ?? "?"}｜区间 ${meta.counts.segments}｜换乘 ${meta.counts.transfers}`,
  );
  if (changed.length === 0) console.log("  所有产物与上次同步一致，未写盘。");
}

await main();
