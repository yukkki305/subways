#!/usr/bin/env node
/**
 * S6-2：把 web/out 发布到 GitHub Pages 的 gh-pages 分支。
 *
 * 为什么不用 `git subtree`：这个仓库的 main 分支根目录不是站点根，
 * 而 Pages 要把「分支根 = 站点根」，用临时仓库 + force push 最干净、也不污染 main。
 *
 * 关键点（见 docs/probe/s6-hosting.md 第四节）：
 *   `out/` 里有 `_next/`、`_not-found/`、`__next.*.txt` 等下划线路径，
 *   GitHub Pages 默认跑 Jekyll 会忽略所有 `_` 开头的文件 → JS/CSS 全 404。
 *   所以发布分支根目录必须带一个空的 `.nojekyll`。
 *
 * 用法：
 *   npm run deploy                # 构建 + 发布
 *   npm run deploy -- --no-build  # 跳过构建，直接发布现有 out/
 *   npm run deploy -- --dry-run   # 只准备 staging 目录，不推送
 */

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, rmSync, statSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";

const WEB_DIR = resolve(import.meta.dirname, "..");
const OUT_DIR = join(WEB_DIR, "out");
const STAGING = join(tmpdir(), "subways-pages");
const BRANCH = "gh-pages";

const argv = process.argv.slice(2);
const noBuild = argv.includes("--no-build");
const dryRun = argv.includes("--dry-run");

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

log(`完成。站点地址：https://yukkki305.github.io/subways/ （首次启用 Pages 后需等 1–2 分钟构建）`);
