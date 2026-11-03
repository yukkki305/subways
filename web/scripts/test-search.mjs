/**
 * S5-1 检索内核的自证脚本。
 *
 *   node scripts/test-search.mjs
 *
 * 直接读仓库里的产物数据（data/processed/shanghai），不依赖浏览器、不依赖 Next。
 * 退出码非 0 表示有用例失败。
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { buildIndex, search } from "../lib/search.ts";

const here = dirname(fileURLToPath(import.meta.url));
const dataDir = resolve(here, "../../data/processed/shanghai");

const stationsFile = JSON.parse(readFileSync(resolve(dataDir, "station.json"), "utf8"));
const linesFile = JSON.parse(readFileSync(resolve(dataDir, "lines.json"), "utf8"));

const index = buildIndex(stationsFile.stations, linesFile.lines);

/** @type {{q: string, expectTitle?: string, expectKind?: "station"|"line", minResults?: number, maxResults?: number, note?: string}[]} */
const cases = [
  { q: "人民", expectTitle: "人民广场", note: "中文子串" },
  { q: "renmin", expectTitle: "人民广场", note: "拼音全拼" },
  { q: "rmgc", expectTitle: "人民广场", note: "拼音首字母" },
  { q: "新闸", expectTitle: "新闸路" },
  { q: "xinzha", expectTitle: "新闸路" },
  { q: "龙阳", expectTitle: "龙阳路" },
  { q: "longyang", expectTitle: "龙阳路" },
  { q: "lyl", expectTitle: "龙阳路" },
  { q: "xjh", expectTitle: "徐家汇" },
  { q: "ljz", expectTitle: "陆家嘴" },
  { q: "一大会址", expectTitle: "一大会址", minResults: 2, note: "两座同名站都要出现；同分时按「名字短者优先」" },
  { q: "ydhz", expectTitle: "一大会址", minResults: 2 },
  { q: "2号线", expectTitle: "2号线", expectKind: "line" },
  { q: "line2", expectTitle: "2号线", expectKind: "line" },
  { q: "磁浮", expectTitle: "磁浮线", expectKind: "line" },
  { q: "爱辉路", expectTitle: "爱辉路", note: "无英文名的站" },
  { q: "迪士尼", expectTitle: "迪士尼" },
  { q: "上海火车站", expectTitle: "上海火车站", minResults: 3, note: "同名三站都要出现（数据里也确实三站）" },
  { q: "人民广场", expectTitle: "人民广场", minResults: 1, maxResults: 1, note: "唯一站，精确命中只出一条" },
  { q: "sjdd", expectTitle: "世纪大道" },
  { q: "zzzz", maxResults: 0, note: "无结果" },
  { q: "   ", maxResults: 0, note: "空输入" },
];

let failed = 0;
const rows = [];

for (const c of cases) {
  const hits = search(index, c.q);
  const top = hits[0];
  let ok = true;
  const reasons = [];

  if (c.expectTitle && !(top && top.title.startsWith(c.expectTitle))) {
    ok = false;
    reasons.push(`首条应为「${c.expectTitle}」，实际「${top ? top.title : "无结果"}」`);
  }
  if (c.expectKind && top && top.kind !== c.expectKind) {
    ok = false;
    reasons.push(`类型应为 ${c.expectKind}，实际 ${top.kind}`);
  }
  if (typeof c.minResults === "number" && hits.length < c.minResults) {
    ok = false;
    reasons.push(`结果数应 ≥${c.minResults}，实际 ${hits.length}`);
  }
  if (typeof c.maxResults === "number" && hits.length > c.maxResults) {
    ok = false;
    reasons.push(`结果数应 ≤${c.maxResults}，实际 ${hits.length}`);
  }
  if (!ok) failed += 1;
  rows.push({
    查询: c.q === "   " ? "(空)" : c.q,
    用例: c.note ?? "",
    首条: top ? `${top.title}${top.kind === "line" ? " [线路]" : ""}` : "—",
    结果数: hits.length,
    结果: ok ? "通过" : `失败：${reasons.join("；")}`,
  });
}

// ---- 性能：423 站 + 20 线，单次查询应当远低于一帧 ----
const probes = ["人民", "renmin", "rmgc", "南", "路", "line", "2", "x", "龙阳路", "shanghai"];
const timings = [];
for (let i = 0; i < 400; i += 1) {
  const q = probes[i % probes.length];
  const t0 = performance.now();
  search(index, q);
  timings.push(performance.now() - t0);
}
timings.sort((a, b) => a - b);
const p50 = timings[Math.floor(timings.length * 0.5)];
const p95 = timings[Math.floor(timings.length * 0.95)];
const max = timings[timings.length - 1];

console.log(`检索用例（索引 ${index.entries.length} 条 = ${stationsFile.stations.length} 站 + ${linesFile.lines.length} 线）\n`);
console.table(rows);
console.log(
  `性能：400 次查询 p50 ${p50.toFixed(3)} ms / p95 ${p95.toFixed(3)} ms / max ${max.toFixed(3)} ms`,
);

if (p95 > 5) {
  console.error(`\n[失败] p95 ${p95.toFixed(3)} ms 超过 5 ms`);
  failed += 1;
}

if (failed > 0) {
  console.error(`\n共 ${cases.length} 条用例 + 1 条性能断言，失败 ${failed} 项。`);
  process.exit(1);
}
console.log(`\n[通过] ${cases.length} 条用例 + 性能断言全部满足。`);
