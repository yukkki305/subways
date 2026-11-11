#!/usr/bin/env node
/**
 * S6-2 / P1a-6.6：把 web/out 发布到 GitHub Pages 的 gh-pages 分支。
 *
 * 为什么不用 `git subtree`：这个仓库的 main 分支根目录不是站点根，
 * 而 Pages 要把「分支根 = 站点根」，用临时仓库 + force push 最干净、也不污染 main。
 *
 * 关键点（见 docs/probe/s6-hosting.md 第四节）：
 *   `out/` 里有 `_next/`、`_not-found/`、`__next.*.txt` 等下划线路径，
 *   GitHub Pages 默认跑 Jekyll 会忽略所有 `_` 开头的文件 → JS/CSS 全 404。
 *   所以发布分支根目录必须带一个空的 `.nojekyll`。
 *
 * 多城（P1a-6.6）：产物里每个 `out/<code>/index.html` 就是一座城的页面（上海在根），
 * 发布前断言「每城都有页面 + cities.json 覆盖」，发布后对线上逐页做冒烟检查。
 *
 * 用法：
 *   npm run deploy                # 构建 + 发布 + 线上冒烟
 *   npm run deploy -- --no-build  # 跳过构建
 *   npm run deploy -- --dry-run   # 只准备 staging，不推送
 *   npm run deploy -- --skip-smoke# 发布但不做线上冒烟
 */

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const WEB_DIR = resolve(import.meta.dirname, "..");
const OUT_DIR = join(WEB_DIR, "out");
const STAGING = join(tmpdir(), "subways-pages");
const BRANCH = "gh-pages";
const SITE = "https://yukkki305.github.io/subways/";

const argv = process.argv.slice(2);
const noBuild = argv.includes("--no-build");
const dryRun = argv.includes("--dry-run");
const skipSmoke = argv.includes("--skip-smoke");

// Windows 上 Node 26 不允许直接 spawn `npm` / `npm.cmd`（ENOENT / EINVAL），
// 统一走 cmd.exe /c，避免 .cmd 的执行策略问题。
const CMD = process.env.ComSpec || "cmd.exe";

function runNpm(args, opts = {}) {
  execFileSync(CMD, ["/d", "/s", "/c", `npm ${args.join(" ")}`], { stdio: "inherit", ...opts });
}

function log(msg) {
  console.log(`[deploy] ${msg}`);
}

function run(cmd, args, opts = {}) {
  return execFileSync(cmd, args, { encoding: "utf8", stdio: "pipe", ...opts }).trim();
}

function step(title) {
  log(`── ${title}`);
}

/** 1. 构建 */
if (!noBuild) {
  step("构建静态导出");
  runNpm(["run", "build"], { cwd: WEB_DIR });
} else {
  step("跳过构建（--no-build）");
}

if (!existsSync(OUT_DIR)) {
  console.error(`[deploy] 找不到 ${OUT_DIR}，先跑一次构建`);
  process.exit(1);
}

/** 产物里实际有哪些城市：上海在根（out/index.html），其余在 out/<code>/index.html。
 *  判据是「有页面 **且** 有 out/data/<code>/meta.json」——只看 index.html 的话，
 *  `404/`、`vendor/` 这类目录也会被当成城市（--dry-run 实测会误报）。 */
function pagesInBuild() {
  const pages = [];
  if (existsSync(join(OUT_DIR, "index.html"))) pages.push({ code: "sh", path: "", file: join(OUT_DIR, "index.html") });
  for (const e of readdirSync(OUT_DIR, { withFileTypes: true })) {
    if (!e.isDirectory() || e.name.startsWith("_") || e.name.startsWith(".")) continue;
    const file = join(OUT_DIR, e.name, "index.html");
    const meta = join(OUT_DIR, "data", e.name, "meta.json");
    if (existsSync(file) && existsSync(meta)) pages.push({ code: e.name, path: `${e.name}/`, file });
  }
  return pages;
}

const pages = pagesInBuild();
if (pages.length === 0) {
  console.error("[deploy] out/ 里没有任何城市页，先跑一次构建");
  process.exit(1);
}

/** 1.5 发布前断言：每页都带城市名，cities.json 覆盖同样的城市集合 */
step("发布前断言");
const citiesJsonPath = join(OUT_DIR, "data", "cities.json");
if (!existsSync(citiesJsonPath)) {
  console.error("[deploy] 缺少 out/data/cities.json（城市切换器会空）");
  process.exit(1);
}
const citiesJson = JSON.parse(readFileSync(citiesJsonPath, "utf8"));
const cityCodes = new Set(citiesJson.map((c) => c.code));
const pagesWithoutData = pages.filter((p) => !cityCodes.has(p.code));
if (pagesWithoutData.length) {
  console.error(`[deploy] 有页面但 cities.json 里没有：${pagesWithoutData.map((p) => p.code).join(", ")}`);
  process.exit(1);
}
const emptyPages = pages.filter((p) => readFileSync(p.file, "utf8").length < 2000);
if (emptyPages.length) {
  console.error(`[deploy] 页面内容异常（<2 KB）：${emptyPages.map((p) => p.code).join(", ")}`);
  process.exit(1);
}
log(`页面 ${pages.length} 个：${pages.map((p) => (p.path || "(根)") + "→" + p.code).join("  ")}`);
log(`cities.json ${citiesJson.length} 条：${citiesJson.map((c) => `${c.code}:${c.lines}线`).join("  ")}`);

/** 2. 准备 staging（out 内容 + .nojekyll） */
step("准备 staging 目录");
rmSync(STAGING, { recursive: true, force: true });
mkdirSync(STAGING, { recursive: true });
cpSync(OUT_DIR, STAGING, { recursive: true });

writeFileSync(join(STAGING, ".nojekyll"), "", "utf8");
log("已写入 .nojekyll（否则 Jekyll 会忽略 _next/）");

// Pages 会用 404.html 兜底未知路径，确认它确实在产物里
if (!existsSync(join(STAGING, "404.html"))) {
  console.error("[deploy] out/ 里没有 404.html，Pages 的自定义 404 会失效");
  process.exit(1);
}

function countFiles(dir) {
  let files = 0;
  let bytes = 0;
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) {
      const sub = countFiles(p);
      files += sub.files;
      bytes += sub.bytes;
    } else {
      files += 1;
      bytes += st.size;
    }
  }
  return { files, bytes };
}

const stats = countFiles(STAGING);
log(`staging：${stats.files} 个文件 / ${(stats.bytes / 1024 / 1024).toFixed(2)} MB`);

/** 3. 提交到临时仓库 */
step("建立临时仓库并提交");
const remote = run("git", ["remote", "get-url", "origin"], { cwd: WEB_DIR.replace(/\\web$/, "") });
const authorName = (() => {
  try {
    return run("git", ["config", "user.name"], { cwd: WEB_DIR });
  } catch {
    return "yukkki305";
  }
})();
const authorEmail = (() => {
  try {
    return run("git", ["config", "user.email"], { cwd: WEB_DIR });
  } catch {
    return "yukkki305@users.noreply.github.com";
  }
})();

const git = (args) => run("git", args, { cwd: STAGING });
git(["init", "-q", "-b", BRANCH]);
git(["config", "user.name", authorName]);
git(["config", "user.email", authorEmail]);
git(["add", "-A"]);
const stamp = new Date().toISOString().replace(/\.\d+Z$/, "Z");
git(["commit", "-q", "-m", `deploy: ${stamp} (${stats.files} files, ${(stats.bytes / 1024 / 1024).toFixed(2)} MB)`]);
const sha = git(["rev-parse", "--short", "HEAD"]);
log(`临时仓库提交 ${sha}`);

if (dryRun) {
  log("--dry-run：不推送，staging 保留在 " + STAGING);
  process.exit(0);
}

/** 4. 推送（带退避重试，见 AGENTS.md 第 11 节） */
step("推送到 " + BRANCH);
const delays = [0, 15_000, 30_000, 60_000, 120_000];
let pushed = false;
for (let i = 0; i < delays.length; i += 1) {
  if (delays[i] > 0) {
    log(`第 ${i + 1} 次重试，等 ${delays[i] / 1000}s`);
    execFileSync(process.platform === "win32" ? "powershell" : "sleep", process.platform === "win32" ? ["-NoProfile", "-Command", `Start-Sleep -Seconds ${delays[i] / 1000}`] : [String(delays[i] / 1000)]);
  }
  try {
    git(["push", "--force", remote, `${BRANCH}:${BRANCH}`]);
    pushed = true;
    log(`推送成功（第 ${i + 1} 次尝试）`);
    break;
  } catch (err) {
    const detail = (err.stderr || err.stdout || String(err)).toString().split("\n").slice(-3).join(" | ");
    log(`第 ${i + 1} 次失败：${detail}`);
  }
}

if (!pushed) {
  console.error("[deploy] 推送失败，staging 保留在 " + STAGING);
  process.exit(1);
}

log(`完成。站点地址：${SITE}（Pages 重建通常 30–60 s）`);

/** 5. 线上冒烟：逐页 + 各城数据 + 城市清单，全部 200 且内容对得上 */
if (skipSmoke) {
  log("--skip-smoke：跳过线上冒烟");
  process.exit(0);
}

async function fetchText(url, timeoutMs = 20000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { signal: ctrl.signal, headers: { "cache-control": "no-cache" } });
    return { status: res.status, text: await res.text(), type: res.headers.get("content-type") ?? "" };
  } catch (err) {
    return { status: 0, text: String(err), type: "" };
  } finally {
    clearTimeout(timer);
  }
}

/** 每城要抽查的数据文件：核心四件 + 底图（上海还有海面） */
function probesFor(code) {
  const base = `${SITE}data/${code}/`;
  const files = ["lines.json", "station.json", "transfer.json", "segment.geojson", "basemap.geojson"];
  const city = citiesJson.find((c) => c.code === code);
  if (city?.has_sea) files.push("sea.geojson");
  return files.map((f) => `${base}${f}`);
}

const pageUrls = pages.map((p) => SITE + p.path);
const allUrls = [
  SITE,
  `${SITE}data/cities.json`,
  ...pageUrls,
  ...pages.flatMap((p) => probesFor(p.code)),
];

step("线上冒烟");
const smokeDelays = [0, 15000, 20000, 30000, 45000];
let smokeOk = false;
let lastReport = "";

for (let attempt = 0; attempt < smokeDelays.length; attempt += 1) {
  if (smokeDelays[attempt] > 0) {
    log(`冒烟第 ${attempt + 1} 轮，等 ${smokeDelays[attempt] / 1000}s（Pages 正在重建）`);
    await new Promise((r) => setTimeout(r, smokeDelays[attempt]));
  }
  const results = await Promise.all(
    allUrls.map(async (u) => ({ url: u, ...(await fetchText(u)) })),
  );
  const bad = results.filter((r) => r.status !== 200);
  // 页面必须含城市名；cities.json 必须是 JSON 且有 4 条
  const pageChecks = pages.map((p) => {
    const r = results.find((x) => x.url === SITE + p.path);
    const city = citiesJson.find((c) => c.code === p.code);
    return { code: p.code, ok: Boolean(r && r.status === 200 && city && r.text.includes(city.label)) };
  });
  const citiesEntry = results.find((r) => r.url === `${SITE}data/cities.json`);
  let citiesOk = false;
  try {
    citiesOk = JSON.parse(citiesEntry.text).length === citiesJson.length;
  } catch {
    citiesOk = false;
  }
  const badPages = pageChecks.filter((p) => !p.ok).map((p) => p.code);

  lastReport = `页面 ${pageChecks.length - badPages.length}/${pageChecks.length}｜数据 ${results.length - bad.length - 1}/${results.length - 1}｜cities.json ${citiesOk ? "ok" : "未就绪"}`;

  if (bad.length === 0 && badPages.length === 0 && citiesOk) {
    smokeOk = true;
    log(`冒烟通过（第 ${attempt + 1} 轮）：${lastReport}`);
    break;
  }
  const detail = [
    bad.length ? `非 200：${bad.slice(0, 3).map((r) => `${r.url.replace(SITE, "")}(${r.status})`).join(", ")}` : "",
    badPages.length ? `页面缺城市名：${badPages.join(",")}` : "",
  ]
    .filter(Boolean)
    .join("；");
  log(`冒烟未通过：${lastReport}｜${detail}`);
}

if (!smokeOk) {
  console.error(`[deploy] 线上冒烟失败：${lastReport}`);
  process.exit(1);
}
log(`线上可用：${pageUrls.join("  ")}`);
