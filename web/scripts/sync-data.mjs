/**
 * 把数据管道的产物复制到 web/public/data/，并写一份 meta.json 供前端显示数据版本。
 *
 * 为什么复制而不是直接读 ../data/processed：
 *   Next.js 静态导出只会打包 public/ 与路由，仓库里的 data/ 在构建产物里不可见；
 *   而把 1.8 MB 数据 import 进 bundle 会让整包在数据更新时整体失效（见 web/README.md）。
 *
 * 用法：node scripts/sync-data.mjs [--check]
 *   --check 只比对、不写盘（CI/校验用）
 */
import { createHash } from "node:crypto";
import { copyFile, mkdir, readFile, stat, writeFile } from "node:fs/promises";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const WEB = resolve(__dirname, "..");
const REPO = resolve(WEB, "..");
const OUT = join(WEB, "public", "data");

/** 需要同步的产物：源路径 → 目标文件名 */
const FILES = [
  ["data/processed/shanghai/lines.json", "lines.json"],
  ["data/processed/shanghai/station.json", "station.json"],
  ["data/processed/shanghai/transfer.json", "transfer.json"],
  ["data/processed/shanghai/segment.geojson", "segment.geojson"],
  ["data/processed/basemap/shanghai-basemap.geojson", "shanghai-basemap.geojson"],
];

const checkOnly = process.argv.includes("--check");

async function sha256(path) {
  const buf = await readFile(path);
  return createHash("sha256").update(buf).digest("hex");
}

async function main() {
  await mkdir(OUT, { recursive: true });

  const entries = [];
  const problems = [];

  for (const [rel, name] of FILES) {
    const src = join(REPO, rel);
    let st;
    try {
      st = await stat(src);
    } catch {
      problems.push(`缺少源文件：${rel}`);
      continue;
    }
    if (!st.isFile()) {
      problems.push(`不是文件：${rel}`);
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
    console.error("[失败] 数据同步：");
    for (const p of problems) console.error("  - " + p);
    process.exit(1);
  }

  // 数据版本信息：前端用来显示「数据截止」，也方便排查前端看到的到底是哪一版
  const station = JSON.parse(await readFile(join(REPO, "data/processed/shanghai/station.json"), "utf8"));
  const totalBytes = entries.reduce((n, e) => n + e.bytes, 0);
  const meta = {
    generated_at: new Date().toISOString(),
    snapshot_date: station.snapshot_date,
    data_as_of: station.as_of ?? station.snapshot_date,
    counts: station.counts,
    total_bytes: totalBytes,
    files: entries.map(({ name, source, bytes, sha256_16 }) => ({ name, source, bytes, sha256_16 })),
  };
  if (!checkOnly) {
    await writeFile(join(OUT, "meta.json"), JSON.stringify(meta, null, 1) + "\n", "utf8");
  }

  const changed = entries.filter((e) => e.changed).map((e) => e.name);
  console.log(`${checkOnly ? "[检查] " : "[同步] "}${entries.length} 个文件 → web/public/data/（${(totalBytes / 1024 / 1024).toFixed(2)} MB）`);
  for (const e of entries) {
    console.log(`  ${e.changed ? "更新" : "一致"}  ${e.name.padEnd(26)} ${(e.bytes / 1024).toFixed(0).padStart(6)} KB  ${e.sha256_16}`);
  }
  console.log(`  快照 ${meta.snapshot_date}｜站 ${meta.counts?.stations ?? "?"}｜站次 ${meta.counts?.slots ?? "?"}｜全线 ${meta.counts?.multi_line_stations ?? "?"} 个多线站`);
  if (changed.length === 0) console.log("  所有产物与上次同步一致，未写盘。");
}

await main();
