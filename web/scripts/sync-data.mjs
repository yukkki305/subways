/**
 * 把数据管道的产物复制到 web/public/data/<code>/，并写每城的 meta.json 与城市清单 cities.json。
 *
 * 为什么复制而不是直接读 ../data/processed：
 *   Next.js 静态导出只会打包 public/ 与路由，仓库里的 data/ 在构建产物里不可见；
 *   而把 1.8 MB 数据 import 进 bundle 会让整包在数据更新时整体失效（见 web/README.md）。
 *
 * 用法：
 *   node scripts/sync-data.mjs [--city <code>] [--all] [--check]
 *     --city   只同步这一座城（默认 sh，也可用环境变量 SUBWAY_WEB_CITY）
 *     --all    同步 pipeline/cities/ 下所有已配置的城市（多城构建用）
 *     --check  只比对、不写盘（CI/校验用）
 *
 * P1a-1.5：城市相关的东西（产物清单、路径、视野、城市名）全部来自
 * pipeline/cities/<code>.json，本脚本不再写死上海。
 * P1a-6.1：输出改为按城市分目录 public/data/<code>/，并生成 cities.json 供切换器使用。
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
const CITIES_INDEX = join(OUT, "cities.json");

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
const allCities = rest.includes("--all");

async function sha256(path) {
  const buf = await readFile(path);
  return createHash("sha256").update(buf).digest("hex");
}

/**
 * 快照标识 → 人类可读日期。
 *
 * 上海的快照是纯日期（20261101），而 p1a 阶段给广州/成都/合肥用的快照名带前缀
 * （p1a-20261103，目录名同时表示「哪一批下载」）。页脚直接显示 p1a-20261103 很难看，
 * 这里只把尾部 8 位数字格式化成 2026-11-03；其它形态原样返回，不猜。
 * meta.snapshot_date 仍保留原值，便于回溯到 data/snapshots/<名>/。
 */
function prettyAsOf(value) {
  if (!value) return null;
  const m = /^[a-z0-9]+-(\d{8})$/.exec(String(value));
  const digits = m ? m[1] : /^\d{8}$/.test(String(value)) ? String(value) : null;
  if (!digits) return String(value);
  return `${digits.slice(0, 4)}-${digits.slice(4, 6)}-${digits.slice(6, 8)}`;
}

/** 同步一座城，返回该城的城市清单条目 */
async function syncCity(code) {
  let cfg;
  try {
    cfg = loadCity(code);
  } catch (err) {
    console.error(`[失败] ${err.message}`);
    console.error(`       可用城市：${listCityCodes().join(" / ")}`);
    process.exit(1);
  }

  const cityDir = join(OUT, code);
  await mkdir(cityDir, { recursive: true });

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
    const dst = join(cityDir, name);
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
    console.error(`[失败] 数据同步（${code}）：`);
    for (const p of problems) console.error("  - " + p);
    console.error(`       提示：先跑 python pipeline/run_city.py --city ${code}`);
    process.exit(1);
  }

  // 数据版本信息：前端用来显示「数据截止」，也方便排查前端看到的到底是哪一版
  const station = JSON.parse(await readFile(join(REPO, cfg.data_dir, "station.json"), "utf8"));
  const lines = JSON.parse(await readFile(join(REPO, cfg.data_dir, "lines.json"), "utf8"));
  const transfer = JSON.parse(await readFile(join(REPO, cfg.data_dir, "transfer.json"), "utf8"));
  const segment = JSON.parse(await readFile(join(REPO, cfg.data_dir, "segment.geojson"), "utf8"));
  const totalBytes = entries.reduce((n, e) => n + e.bytes, 0);
  const has = (n) => entries.some((e) => e.name === n);
  const meta = {
    generated_at: new Date().toISOString(),
    city_code: cfg.code,
    city: cfg.name,
    city_label: cityLabel(cfg),
    snapshot_date: station.snapshot_date,
    data_as_of: prettyAsOf(station.as_of ?? station.snapshot_date),
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
    await writeFile(join(cityDir, "meta.json"), JSON.stringify(meta, null, 1) + "\n", "utf8");
  }

  const changed = entries.filter((e) => e.changed).map((e) => e.name);
  console.log(
    `${checkOnly ? "[检查] " : "[同步] "}${meta.city_label}（${cfg.code}）${entries.length} 个文件 → web/public/data/${cfg.code}/（${(totalBytes / 1024 / 1024).toFixed(2)} MB）`,
  );
  for (const e of entries) {
    console.log(`  ${e.changed ? "更新" : "一致"}  ${e.name.padEnd(20)} ${(e.bytes / 1024).toFixed(0).padStart(6)} KB  ${e.sha256_16}`);
  }
  console.log(
    `  快照 ${meta.snapshot_date}｜线路 ${meta.counts.lines}｜车站 ${meta.counts.stations ?? "?"}｜区间 ${meta.counts.segments}｜换乘 ${meta.counts.transfers}`,
  );
  if (changed.length === 0) console.log("  所有产物与上次同步一致，未写盘。");

  return {
    code: cfg.code,
    label: meta.city_label,
    city: cfg.name,
    lines: meta.counts.lines,
    stations: meta.counts.stations ?? 0,
    segments: meta.counts.segments,
    transfers: meta.counts.transfers,
    snapshot_date: meta.snapshot_date,
    has_basemap: has("basemap.geojson"),
    has_sea: has("sea.geojson"),
    bytes: totalBytes,
  };
}

async function main() {
  await mkdir(OUT, { recursive: true });

  const codes = allCities ? listCityCodes() : [city];
  const synced = [];
  for (const code of codes) {
    synced.push(await syncCity(code));
  }

  // 城市清单：只记录磁盘上确实同步过的城（--city gz 时不能把上海的条目覆盖掉）
  let index = [];
  try {
    index = JSON.parse(await readFile(CITIES_INDEX, "utf8"));
    if (!Array.isArray(index)) index = [];
  } catch {
    index = [];
  }
  const byCode = new Map(index.map((c) => [c.code, c]));
  for (const c of synced) byCode.set(c.code, c);
  const merged = [...byCode.values()].sort((a, b) => a.code.localeCompare(b.code));
  if (!checkOnly) {
    await writeFile(CITIES_INDEX, JSON.stringify(merged, null, 1) + "\n", "utf8");
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

  console.log(`\n城市清单：${merged.map((c) => `${c.code}(${c.label})`).join(" / ")} → web/public/data/cities.json`);
}

await main();
