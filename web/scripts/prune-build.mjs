#!/usr/bin/env node
// 构建清理：Turbopack 会把 maplibre 的所有构建变体登记进 out/_next/static/media/，
// 但本页只用 public/vendor/maplibre-gl-worker.mjs（显式 setWorkerUrl），
// media/ 下的副本浏览器一次都不会请求（实测见 docs/validation-s3.md 第 5 节）。
// 删掉它们不影响功能：删光后重跑仍 loaded=true、589 段线路、80 个换乘点、0 报错。
//
// 用法：
//   node scripts/prune-build.mjs             # 删除 media/ 下的 maplibre 副本（默认）
//   node scripts/prune-build.mjs --all       # 清空 media/（未来若引入其它库）
//   node scripts/prune-build.mjs --dry-run   # 只报告
import { readdirSync, statSync, unlinkSync } from "node:fs";
import { join } from "node:path";

const args = process.argv.slice(2);
const all = args.includes("--all");
const dry = args.includes("--dry-run");
const OUT = join(process.cwd(), "out", "_next", "static", "media");

let entries;
try {
  entries = readdirSync(OUT);
} catch {
  console.error(`找不到 ${OUT}，先跑 npm run build`);
  process.exit(1);
}

const victims = [];
let freed = 0;
for (const name of entries) {
  const full = join(OUT, name);
  const size = statSync(full).size;
  const empty = size === 0;
  const maplibre = name.startsWith("maplibre-gl");
  if (empty || (all ? true : maplibre)) {
    victims.push({ name, size, why: empty ? "0 字节占位" : "运行时不请求的副本" });
    freed += size;
  }
}

if (!victims.length) {
  console.log("media/ 里没有需要清理的文件");
  process.exit(0);
}

for (const v of victims) {
  if (!dry) unlinkSync(join(OUT, v.name));
  console.log(`${dry ? "将删除" : "已删除"} ${v.name.padEnd(48)} ${(v.size / 1048576).toFixed(2)} MB  (${v.why})`);
}
console.log(`\n${dry ? "可释放" : "已释放"} ${(freed / 1048576).toFixed(2)} MB，共 ${victims.length} 个文件`);
