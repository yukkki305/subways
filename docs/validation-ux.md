# UX 自证：总览页 + 深色主题（阶段 0–4）

> 对应计划：`docs/plan-ux.md`。本文只记录**可复现的证据**：命令、数字、失败过什么。
> 阶段 5（发布）另见发布冒烟输出与线上页面。

## 一、结论

| 项 | 结果 |
| --- | --- |
| 五个页面 | `/`、`/cities/`、`/gz/`、`/cd/`、`/hf/` 构建期全部静态产出 |
| 深色主题 | 界面 + 地图两层都跟随；三态切换（浅色 / 深色 / 跟随系统）刷新后保持 |
| 首帧 | 深色下第一帧地图就是 `#1A1A18`，无浅色闪帧（88 / 162 / 240 ms 三点采样） |
| 浅色回归 | 地图 21 层逐一回读与改造前同值；界面颜色 token 化后视觉无变化 |
| 校验 | `npm run verify` **94 项 / 4 城 / 0 失败**；反向验证各 1 项失败 |
| 体积 | 导出 8.37 MB（staging），`/cities/` 单页 175 KB |

## 二、验收对照（U-A1…U-A7）

| 编号 | 判定 | 证据 |
| --- | --- | --- |
| U-A1 五页可打开 | ✅ | 构建路由表 `○ /`、`○ /cities`、`● /gz`、`● /cd`、`● /hf`；`verify` 逐页断言存在且含城市名 |
| U-A2 总览数字一致 | ✅ | 卡片计数取自 `public/data/cities.json`，`verify` 断言其与各城 `meta.counts` 一致（含 `stations`）；反向验证把 hf 改成 999 → 恰好 1 项失败 |
| U-A3 可读性 | ✅（修过一处） | 见第三节对比度表；浅色 `--c-text-subtle` 原 `#8b8374` 只有 **3.33:1**，已压深为 `#6f6a5c`（4.83:1） |
| U-A4 主题行为 | ✅ | 见第四节：持久化、循环、跟随系统、首帧无闪 |
| U-A5 深色地图 | ✅ | 21 层全部换色（`PALETTE_PAINT` 20 条 + 3 个双语层 layout）；线色未动（D6）；缩放控件深色化 |
| U-A6 校验与体积 | ✅ | 94 项全绿；导出 8.37 MB < 10 MB（ADR 0005） |
| U-A7 线上 | ✅ | 冒烟第 5 轮通过：页面 5/5、数据 27/27、`cities.json` ok；线上四城 `map.loaded()` 全 true、`background=#1A1A18`、`basemap` 源存在；总览页 `ttfb 114 ms` |

## 三、对比度（实测渲染值，非设计值）

用浏览器读 `getComputedStyle` 的实际颜色算 WCAG 比值：

| 位置 | 主题 | 前景 / 背景 | 比值 |
| --- | --- | --- | --- |
| 卡片元信息 | 浅色 | `rgb(63,58,50)` / `rgb(255,255,255)` | 11.27 |
| 页脚版权 | 浅色 | `rgb(111,106,92)` / `rgb(244,242,238)` | **4.83** |
| 卡片元信息 | 深色 | `rgb(207,203,194)` / `rgb(38,38,35)` | 9.38 |
| 页脚版权 | 深色 | `rgb(143,138,129)` / `rgb(26,26,24)` | 5.08 |
| 抽屉站序表 | 深色 | `rgb(168,163,154)` / `rgba(38,38,35,.94)` | 6.05 |
| 抽屉正文 | 深色 | `rgb(233,230,223)` / `rgba(38,38,35,.94)` | 12.17 |

判据：正文级 ≥ 4.5:1。修前 `#8b8374` 在纸底上是 3.33:1（不达标），所以改了 token 而不只是放宽标准。

## 四、主题行为 E2E（真实 bundle，非单测）

| 场景 | 做法 | 结果 |
| --- | --- | --- |
| 深色持久化 | `localStorage["subways-theme"]="dark"` 后重载 | `data-theme=dark`、`window.__THEME__="dark"`；采样 88/162/240 ms 的 `background` 均为 `#1A1A18` |
| 切换后刷新 | 点一次（dark→system→light）后 `reload` | `data-theme=light`、`__THEME__="light"`、`localStorage="system"` |
| 跟随系统 | 打桩 `window.matchMedia` 令 `prefers-color-scheme: dark` 为 true，再循环到「跟随系统」 | `data-theme=dark`、地图 `background=#1A1A18`、按钮文案「跟随系统」 |

**做不到的**：这套 ego 运行时里 `Emulation.setEmulatedMedia` 对 `matchMedia` 不生效（设了 `prefers-color-scheme=dark` 后 `matches` 仍是 false），所以「系统主题变化时实时跟随」只能靠打桩验证解析路径 + 代码里 `mql.addEventListener("change")` 的存在，无法在真机上模拟系统切换。

## 五、校验增项（87 → 94）

| 增项 | 断言 | 失败时说明什么 |
| --- | --- | --- |
| 总览页存在 | `out/cities/index.html` 存在且 > 2 KB | 路由没生成 |
| 总览页收录 | `out/sitemap.xml` 含 `cities/` | SEO 漏页 |
| 四城齐全 | HTML 里四个城市名都在 | 某城卡片丢了 |
| 缩略图有内容 | `<path>` 数（63）> 城市数（4） | 缩略图退化成一堆空框 |
| 卡片链接正确 | 上海 `href="/subways/"`、其余 `href="/subways/<code>/"` | 点了进错城 |
| 浅色纸色一致 | `globals.css` 的 `--c-paper` == `LIGHT.paper` | 界面与地图底色差一圈 |
| 深色纸色一致 | 深色块 `--c-paper` == `DARK.paper` | 同上，深色下更明显 |

反向验证（各改一处、确认恰好 1 项失败后再改回）：

- `hf` 的 `cities.json` 里 `stations` 改 999 → `[hf] cities.json 条目与 meta 一致 — 8/999/207/0`。
- 深色 `--c-paper` 改 `#000000` → `深色 --c-paper 与 lib/theme.ts 同值 — #000000 / #1a1a18`。

解析坑：`globals.css` 文件头注释里也写了 `:root[data-theme="dark"]`，用 `indexOf` 切段会把 light 段切在注释处（第一版就是这么错的，报 `解析失败（css=null theme=#f4f1ea）`）。最终用行首选择器 `^:root\[data-theme="dark"\]\s*\{` 定位。

## 六、发布侧改动（`deploy.mjs`）

总览页没有 `data/<code>/meta.json`，不会进 `pagesInBuild()`，所以单独登记 `overviewPage`：

- 发布前：`总览页：cities/（175 KB）`；
- 冒烟：总览页必须 200、含「全部城市」、且四城名全部出现（缺一张卡 = 某城进不去）；
- `--dry-run` 实测：`页面 4 个：(根)→sh cd/→cd gz/→gz hf/→hf`、`cities.json 4 条`、`staging：80 个文件 / 8.37 MB`。

## 七、已知局限

1. 缩略图是**全网络等比**，不裁市区：上海/广州有远郊线，市中心看起来比合肥小。裁主城区会暗示合肥更密，故不做。
2. 暗底上偏深的线路（广州 14 号线暗栗、合肥深绿）对比度偏低，只有 casing 留白分隔；按 D6 不调线色。
3. 加载遮罩改成不透明（阶段 2 修复首帧闪色），代价是首屏多遮一帧 —— 实测 `dcl` 未变。
4. 缩略图在构建期生成，改了 `segment.geojson` 必须重新 `npm run build` 才会更新。
5. 主题存在 `localStorage`，无 cookie、无服务端偏好，SSR 首屏永远是浅色 HTML（由 `THEME_INIT` 在样式前改 `data-theme`）。

## 八、复现命令

```powershell
cd E:\subway\web
npm run sync -- --all          # 四城数据 → public/data/<code>/
npm run build                  # 静态导出 out/（含 /cities/）
npm run verify                 # 94 项 / 4 城
npm run test:search            # 61 条用例
node scripts/deploy.mjs --dry-run   # 发布前断言（不推送）
```

本地预览：`node E:\subway-data\probe-ux\serve.mjs` → `http://127.0.0.1:4402/subways/`，带 `?v=N` 绕过缓存。

## 九、两条教训

1. **「通过」必须能被证明**：新加的断言先做反向验证（改坏一处 → 恰好 1 项失败），否则等于什么都没查。
2. **首帧问题只能靠采样抓**：肉眼看不到 215 ms 的浅色帧，必须主动按时间点回读 `getPaintProperty`。
