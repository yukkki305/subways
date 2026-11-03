# web：前端

Next.js 16（App Router + **静态导出**）渲染上海地铁图。数据全部来自仓库里的 `data/processed/`，构建前复制到 `public/data/`，前端不做运行时外部请求（AGENTS.md 第 3 节）。

## 命令

```powershell
$env:Path = 'E:\node;' + $env:Path      # 会话内工具进程可能继承旧环境
cd E:\subway\web
& E:\node\npm.cmd run sync              # 单独同步数据（predev / prebuild 会自动跑）
& E:\node\npm.cmd run dev               # 开发服务器 http://127.0.0.1:3210
& E:\node\npm.cmd run build             # 静态导出到 web\out\
& E:\node\npm.cmd run typecheck         # tsc --noEmit
& E:\node\npm.cmd run verify            # 构建自证：21 项静态检查（S3-7 / S4-7，含打包残留）
& E:\node\npm.cmd run test:search       # 检索内核用例（S5-1，22 条 + 性能断言）
```

看导出结果（`next start` 不适用于静态导出）：

```powershell
D:\python\python3.14.6\python.exe -m http.server 3210 --bind 127.0.0.1   # 在 web\out\ 下执行
```

## 数据同步（S3-2）

`scripts/sync-data.mjs` 把数据管道的 5 个产物复制到 `public/data/`，并在同目录写 `meta.json`：

| 复制文件 | 源 | 大小 |
| --- | --- | --- |
| `lines.json` | `data/processed/shanghai/lines.json` | 42 KB |
| `station.json` | `data/processed/shanghai/station.json` | 431 KB |
| `transfer.json` | `data/processed/shanghai/transfer.json` | 17 KB |
| `segment.geojson` | `data/processed/shanghai/segment.geojson` | 841 KB |
| `shanghai-basemap.geojson` | `data/processed/basemap/shanghai-basemap.geojson` | 484 KB |

合计 1.77 MB。行为约定：

- **幂等**：逐文件比 sha256，一致则跳过（实测第二次跑输出「一致…未写盘」）
- **缺文件即失败**：任一源文件不存在，打印缺失清单并 `exit 1`，不生成半套数据
- **`--check` 只比对不写盘**，用于校验前端数据与管道产物是否一致
- `meta.json` 带 `snapshot_date` / `data_as_of` / `counts` / 每文件 `sha256_16`，前端用它显示「数据截止」并排查版本错配
- `public/data/` 与 `out/` 都在 `web/.gitignore` 里，**不进 git**（实测 `git check-ignore` 命中）

## 依赖

| 包 | 版本 | 说明 |
| --- | --- | --- |
| next | 16.4.3 | `output: "export"`，`trailingSlash: true` |
| react / react-dom | 19.3.1 | Next 16 要求 React 19 |
| maplibre-gl | 6.16.0 | 无 Token；中文标签走本机 TinySDF（探测 7：**不要给 CJK 配 glyph PBF**） |

安装：`npm install --registry=https://registry.npmmirror.com`（官方源实测 17 KB/s，镜像 167 KB/s）。

## 目录

| 路径 | 用途 |
| --- | --- |
| `app/` | 路由与全局样式（`layout.tsx` / `page.tsx` / `globals.css`） |
| `components/MapView.tsx` | 地图组件：取数 → 建样式 → fitBounds → 版权与状态层（S3-3） |
| `lib/mapStyle.ts` | 底图/线路的样式常量、`buildStyle()`、`boundsOf()` |
| `scripts/sync-data.mjs` | 把 `../data/processed/*` 复制到 `public/data/`，并把 maplibre worker 拷到 `public/vendor/` |
| `public/data/` | 复制产物，**不进 git**（`.gitignore`） |
| `public/vendor/` | maplibre render worker 原件，**不进 git** |
| `out/` | 静态导出结果，**不进 git** |

## 两个必须知道的坑

**1. maplibre 的 render worker 由 Next 打包会算错 URL** —— 浏览器控制台报 `Worker failed to load. Check that the worker URL is correct.`，地图永远停在加载态。修法是 `sync-data.mjs` 把 `node_modules/maplibre-gl/dist/maplibre-gl-worker.mjs` 拷到 `public/vendor/`，前端创建地图前调用：

```ts
maplibregl.setWorkerUrl("/vendor/maplibre-gl-worker.mjs");
```

**2. maplibre 会给容器加 `.maplibregl-map { position: relative }`**，覆盖掉 `.map-canvas { position: absolute; inset: 0 }`，容器高度塌成 0。必须显式写 `width: 100%; height: 100%`。

## S3-3 地图骨架（已完成）

- 单一入口 `components/MapView.tsx`（`"use client"`），`useEffect` 里一次性完成取数 + 建图，卸载时 `map.remove()`
- 取 4 个文件：`shanghai-basemap.geojson`、`segment.geojson`、`lines.json`、`meta.json`（失败只降级、不白屏）
- 图层顺序（底 → 顶）：`background` → `water-fill` → `coastline` → `water-line` → `district-line` → `province-line` → `metro-line`
- 线路颜色来自 `lines.json` 的 `colour`，用 `["match", ["get","line_id"], …]` 表达式注入，前端不硬编码
- 视野用 `boundsOf(segment.geojson)` + `fitBounds(padding 72/96/48/48)`，不用底图范围（底图含整个长江口）
- 自查钩子：`window.__map`（E2E 读相机/图层）、`window.__mapErrors`（收集 maplibre 报错）

## S3-4 站点与站名分层（已完成）

站点从 `station.json`（430 条）转成 GeoJSON，三层压在线的上面：

| 图层 | 类型 | 阈值 | 说明 |
| --- | --- | --- | --- |
| `station-dot` | circle | zoom ≥ 10 | 普通站：白填充 + 灰描边，半径 z10 1.6 → z17 4.6 |
| `station-dot-transfer` | circle | zoom ≥ 10 | 换乘站（`is_transfer`）：半径更大、描边更深（#2B2B2B） |
| `station-label` | symbol | **zoom ≥ 11** | 站名左对齐在圆点右侧，`text-padding 3` + 自动避让 |

实测（`queryRenderedFeatures`）：

| 缩放 | 站名 | 圆点 |
| --- | --- | --- |
| z10.95 | **0** | 415 |
| z11.15 | 201（碰撞避让后） | — |
| z12.2 | 143 | 210（普通 156 + 换乘 54） |
| z13.0 | 61 | — |

**同名多站的显示规则**：ADR R4 里 >300 m 不合并的 12 组（上海火车站、静安寺、南京西路、陆家嘴、浦东南路等）在地图上会重名，`stationsToGeoJSON()` 给同名的第 2、3 个加 `(2)`、`(3)` 后缀（按经度排序，编号稳定）。只改 `name_display`，`name` 保持 OSM 原值。

坑：`text-field` 若直接用 `name`，两个「上海火车站」并排出现会被当成 bug 报上来 —— 用之前先把重名处理掉。

## 约定

- 客户端组件才碰 `window` / WebGL；地图初始化放 `useEffect` 或 `next/dynamic({ ssr: false })`
- 数据走 `fetch('/data/*.json')`，不要 `import` 进 bundle（1.8 MB 数据不该进 JS 包）
- 站点/线路的颜色一律取自 `lines.json` 的 `colour`，不在前端硬编码

## S3-5 点击详情（已完成）

点站点圆点或站名 → 右侧抽屉显示该站详情；Esc、右上角 ×、点空白处均可关闭。

| 交互 | 行为 |
| --- | --- |
| 点击 `station-dot` / `station-dot-transfer` / `station-label` | `queryRenderedFeatures(e.point, {layers: PICK_LAYERS})` 取 `properties.id`，命中即选中 |
| 点空白 | `setSelectedId(null)` |
| 悬停 | `mouseenter/mouseleave` 改手型 |
| Esc | 关闭抽屉 |
| 抽屉内点「同站名换乘」的对端站名 | `easeTo` 到该站并切换详情 |

- 选中态写入 `selected` 空源，由 `station-selected` 图层画外圈（半径 z10 6 → z17 13），压在站名之下
- 详情内容全部来自 `station.json` / `lines.json` / `transfer.json`，**前端不臆造**：`walk_minutes` 显示为「无可靠来源，一律留空」
- 同名多站编号 `(1)(2)(3)` **跟着 station id 的后缀走**（`-2` → (2)），保证地图标签、抽屉标题、`站 id` 三处说的是同一个数字
- 站序的上一站/下一站由 `lines.json` 的 `branch.stops` 按 `slot.seq` 取，环线首尾相接
- `web/lib/dataset.ts` 是唯一的数据形状与派生逻辑（`displayNames` / `transfersOf` / `neighborsOf` / `stationsToGeoJSON`），`mapStyle.ts` 不再重复实现

E2E 实测（CDP 真实鼠标事件）：点击人民广场圆点 → 抽屉「人民广场」、3 条线路 chips、zoom 不变；点击「徐家汇」标签文字 → 抽屉「徐家汇(1)」；Esc 与点空白处均关闭；上海南站(1) 抽屉正确列出与 (2)(3) 的两条「出站换乘」、254 m / 188 m、medium 置信度。

## S3-6 视觉打磨（已完成）

### 线路：纸色描边 + 分层宽度

| 图层 | 作用 | 宽度（z8 → z17） |
| --- | --- | --- |
| `metro-line-casing` | 纸色（`PALETTE.paper`）描边，垫在线路下 | 3.4 → 4.6 → 6.0 → 7.6 → 11.5 |
| `metro-line` | 线路本体（颜色来自 `lines.json` 的 `colour`） | 1.4 → 2.0 → 3.0 → 4.2 → 7 |

描边不是装饰：两条线交叉时，后画的线会盖住前一条，读者会误以为那条线断了。加一层同色纸的「casing」后，交叉处出现 1–2 px 留白，线路的连续性一眼可辨（对比 `s3-6-z13.png` 与 S3-5 截图）。

### 站点：按缩放分三档

| 缩放 | 显示 |
| --- | --- |
| < 9.5 | 只有线路（全城概览） |
| 9.5 – 11 | 换乘站圆点（80 个，给概览一点地标感） |
| 11 – 12.6 | 换乘站点 + **换乘站站名**；普通站点只有小圆点 |
| ≥ 12.6 | 普通站站名也出现（`station-label-minor`，更小更浅） |

站名分 `station-label-major`（换乘站，11 px→15 px，`symbol-sort-key: line_count`）与 `station-label-minor`（普通站，10.5 px→13 px）。`text-max-width` 设为 12，避免「一大会址·黄陂南路」这类长名折行。

### 悬停

`mousemove` 命中的站点写入 `hover` 源，由 `station-hover-label` 在圆点上方浮出站名（`maxzoom 12.55`，只在常驻站名还没出现的区间生效，避免和大图标签重复）。鼠标变手型。

### 首屏与加载

- 加载浮层 `.map-loading`：脉冲红点 + 「正在铺开上海地铁图」+ 副行数量说明；失败态换文案并 `role="alert"`；`prefers-reduced-motion` 下关动画
- **fitBounds 时序**：`map.on("load")` 里必须先 `map.resize()`，再用 `requestAnimationFrame` 检查 `canvas.clientWidth/clientHeight ≥ 10` 后才 `fitBounds`。否则容器高度还是 0 时算出的缩放极大（实测会跳到 z15.1，只显示 6 条线）

实测（`queryRenderedFeatures` 计数）：

| 缩放 | 换乘站名 | 普通站名 | 换乘点 | 普通点 |
| --- | --- | --- | --- | --- |
| 9.59（首屏） | 0 | 0 | 80 | 0 |
| 11.2 | 57 | 0 | 74 | 228 |
| 12.9 | 32 | 43 | 29 | 44 |

## S4-1 字体（已完成）

**不引入任何字体资产**（S4-1 决策 D1-A）：中文与西文都由浏览器本机渲染。

- 字体栈集中在一处：`lib/typography.ts` 的 `FONT_STACK`（给 `text-font`）与 `FONT_STACK_CSS`（给 `localIdeographFontFamily` 和 CSS）。当前是 `Microsoft YaHei UI → Microsoft YaHei → PingFang SC → Hiragino Sans GB → Noto Sans SC → sans-serif`，Windows 用雅黑、macOS 落苹方。
- 三个 symbol 图层（`station-label-major` / `station-label-minor` / `station-hover-label`）都写了 `text-font: FONT_STACK`；`MapView` 里 `localIdeographFontFamily` 用同一个串。
- **为什么要两边都写**：读 maplibre-gl 6.16.0 源码（`GlyphManager._getTinySDF`）可知，只有 `text-font` 等于默认栈时才会用 `localIdeographFontFamily`；一旦显式写 `text-font`，就用该栈本身当 CSS 字体串。两边写成同一个栈，中文和西文才不会各走各的。
- 实测：`glyph PBF 请求 0 次`、字体文件请求 `0 次`、z12.85 下 76 个标签正常出字。
- 换字体只改 `lib/typography.ts`；将来切 D1-B（自托管 Noto Sans SC 子集，约 57 KB）走 `font-faces`，把 `text-font` 换成字体名即可。

**已知限制**：本机渲染不受字形 hinting 控制，极小字号（<10px）会略糊；国际化的英文副标题留给 S4-2。

## S4-2 英文站名（已完成）

z13 起站名改为「中文一行 + 英文小字一行」，中英写在**同一个 label** 里。

- 用 `format` 表达：`["format", ["get","name_display"], {font-scale:1}, "\n", ["get","name_en"], {font-scale:0.66, text-color:"#6E6E6E"}]`。放在一个 label 里，碰撞检测把一个站算作整体，不会出现「中文留下了、英文被挤掉」。
- `station-label-major` / `station-label-minor` 都加了 `maxzoom: 13`，从 z13 起交接给双语层。
- **按英文名长度分三档**（英文名长短差异极大）：
  | 图层 | 触发条件 | 效果 |
  | --- | --- | --- |
  | `station-label-bilingual` | z13 起，`name_en` 长度 ≤ 30 | 中英双语 |
  | `station-label-long-zh` | z13–15，长度 > 30 | 只出中文，避免一屏折行英文 |
  | `station-label-bilingual-long` | z15 起，长度 > 30 | 中英双语（如「一大会址·黄陂南路 / Site of the First CPC National Congress·South Huangpi Road」） |
- 没有英文名的 3 站（爱辉路、长江西路、通南路）只出中文；`filter` 里显式排除了空值。
- 版式：`text-size` z13 12 → z15 13.5 → z17 15.5、`text-anchor/text-justify: left`、`text-offset [0.85,0]`、`text-max-width 16`、`text-line-height 1.02`。
- 点击命中层 `PICK_LAYERS` 扩到 5 个来源图层，双语层与「只中文」层都能被点到。

实测（`queryRenderedFeatures` 计数）：z12.9 → minor 42 / major 32（中文单层）；z13.4 → 双语 36；含长名站的视野 z13.3 → 只中文 3 + 双语 40；z15.6 → 双语 1 + 长名双语 1。

## S4-3 制式线型（已完成）

不同制式用不同线型，全部由 `lines.json` 的 `type` 推导，数据层不加字段（S4-3 决策 D4-A）：

| 制式 | 图层 | 线型 | 依据 |
| --- | --- | --- | --- |
| `metro` | `metro-line` | 实线 | 18 条地铁 |
| `maglev` | `maglev-line` | 虚线 `[2.6, 2.0]`（线宽倍数） | 磁浮线 |
| `apm` | `apm-line` | 点线 `[0.05, 1.6]` + 圆头 | 浦江线（胶轮路轨） |

- `buildStyle(basemap, segments, stations, lineColors, lineTypes)` 新增第 5 个参数；`idsOfType()` 从「id → type」里挑出某一类，写成 `["in", ["get","line_id"], ["literal", ids]]` 的 filter。
- 三条线型层共用下面那层 `metro-line-casing`（纸色描边无 filter），所以虚线/点线在交叉处同样有留白。
- `metro-line` 的 filter 反过来排除了这两类，避免同一条线被画两遍（计数：实线 582 + 磁浮 2 + 浦江 5 = 589 段，与总数一致）。
- **踩坑**：`line-dasharray` **不接受表达式**，只能是字面量数组；写成 `["interpolate", …]` 会整页白屏并报 `layers[8].paint.line-dasharray[4][0]: Expression name must be a string`。

## S4-4 海面（已完成）

背景色即陆地，海面单独一层填色，岛屿由海面自身的「洞」表达。

- 数据由 `pipeline/14_extract_sea.py` 生成：读五省 PBF，收集 `natural=coastline`（视野内 上海 130 / 江苏 42 / 浙江 433 / 安徽 0 / 山东 0 条），与 bbox 边框一起 `polygonize`，**bbox 减掉全部陆地faces = 海面**；再删掉 <0.05 km² 的针孔洞。
- 产物 `data/processed/basemap/shanghai-sea.geojson`：**1 个面 / 24,829.3 km² / 2,562 顶点 / 91,741 B**，含 76 个岛洞（崇明、长兴、横沙、洋山等）。
- 前端：`mapStyle` 新增 source `sea` 与最底层填充层 `sea-fill`（`PALETTE.sea = #DCE6EF`），顺序 `background → sea-fill → water-fill → coastline → …`。四层验证：4 个海测试点进入、人民广场/崇明/长兴/滴水湖都在陆上。
- **不能只用上海一份**：S4-0 已证 shanghai extract 的 130 段 coastline 有 32 个连通分量、8 个自由端点，拼出来是包围整个 bbox 的 39,454 km² 假面。
- **踩坑（判定口径）**：长江口北支在 OSM 里由河岸而非 coastline 围成，若把测试海点放进去（如 `121.90,31.70`），整块上海陆地会被判成海（面积跳到 37,852 km²、人民广场落水）。最终只用三个毫无歧义的外海点。
- 副产物：`verify-build.mjs` 的数据文件清单加 `sea.geojson`，静态检查 20 → **21 项**。

## S4-5 站点符号（已完成）

统一成「白心 + 深灰环」，换乘站再强化一层（S4-5 决策 D5-A）：

| 图层 | 作用 | 关键参数 |
| --- | --- | --- |
| `station-transfer-halo` | 换乘站底下垫一圈纸色，把压着的线路「挖」掉，符号不再糊在线条里 | 半径比圆点大 1.6–2.0 px，`PALETTE.paper` 95% |
| `station-dot` | 普通站：白心 + 细灰环 | 半径 z11 2.0 → z17 5.6；环 `#6E6E6E`，0.9 → 1.7 |
| `station-dot-transfer` | 换乘站：白心 + 粗深环 | 半径 z9.5 2.2 → z17 7.0；环 `#2B2B2B`，1.0 → 2.6 |
| `station-selected` | 选中站外圈（点击后） | `PALETTE.ink` 2.4 |

- 三层都进了 `PICK_LAYERS`，点圆点、点外圈光晕、点站名都能开抽屉。
- 为什么加 halo：换乘站多压在两三条线交汇处，只画白心圆点时线条会从符号缝里透出来，远看像脏点；垫一层纸色后符号边界干净。
- 实测 z13.4：换乘点 16 / 光晕 16 / 普通点 25；点人民广场（`[121.470436, 31.234642]`）→ 抽屉显示 3 条线路、3 行站序、合并方式「150–300 m 合并待复核」。

## S3-7 构建自证（已完成）

`scripts/verify-build.mjs` 只做静态检查，不启浏览器，任何机器可重跑：

```powershell
& E:\node\npm.cmd run build
& E:\node\npm.cmd run verify      # 21 项，失败即 exit 1
```

覆盖：入口 HTML、无外部资源、7 个数据文件齐全（含 `sea.geojson`）、20 线/430 站/22 换乘/570 段、`meta.json` 计数与字节数自洽、车站坐标全在 WGS-84 上海视野内（防 GCJ-02 混入）、颜色为合法十六进制、总体积上限。

浏览器端断言（图层顺序、首屏视野、点击/`Esc`/点空白/悬停、0 glyph 请求、0 个 4xx、0 个 JS 错误）记录在 [`docs/validation-s3.md`](../docs/validation-s3.md)。

首屏 16 个请求、未压缩 3.98 MB、gzip 后约 **0.75 MB**。

**打包清理（已修）**：`out/_next/static/media/` 里 Turbopack 会登记 maplibre 的全部构建变体（dev 2.49 MB + worker-dev 1.20 MB + 生产 1.11 MB + worker 0.52 MB + css 0.07 MB + 两个 0 字节占位，共 5.14 MB），浏览器一个都不请求（worker 走 `setWorkerUrl("/vendor/…")`）。

`scripts/prune-build.mjs` 挂在 `postbuild` 上自动清掉：

```powershell
& E:\node\npm.cmd run prune -- --dry-run   # 只报告
& E:\node\npm.cmd run prune                # 删除 media/ 下 maplibre* 与 0 字节文件
& E:\node\npm.cmd run prune -- --all       # 清空 media/（将来引入其它库时用）
```

产物 **9.10 MB → 3.96 MB（34 个文件）**，gzip 约 0.89 MB；删光 `media/` 后实测 `loaded` 仍为真、589 段线路、80 个换乘点、0 报错。`verify-build.mjs` 已把「media/ 无 maplibre 残留」「无 -dev. 残留」「总体积 < 8 MB」列为断言。

## S4-6 排版终校（已完成）

字号、间距、圆角统一收到 `globals.css` 的 `:root` 变量里，改一处即可全局生效：

| 变量 | 值 | 用途 |
| --- | --- | --- |
| `--fs-meta` | 10.5px | 页脚、表头、次要说明 |
| `--fs-small` | 11.5px | 抽屉副标题、`dl.kv` |
| `--fs-body` | 12.5px | 抽屉正文 |
| `--fs-title` / `--fs-h2` | 15px / 17px | 页面标题 / 抽屉站名 |
| `--sp-1..4` | 4 / 8 / 12 / 16px | 内边距与段间距 |
| `--radius-sm/md/lg/pill` | 6 / 10 / 12 / 999px | 控件圆角 |

具体修的四件事：

1. **抽屉高度随内容走**：原来 `bottom: 56px` 固定撑到底，人民广场只有 3 行站序时会留一大片空白；改成 `max-height: calc(100% - 96px)`，实测 340×505。
2. **站序表加内边距**：`th/td` 统一 `padding: 0 10px 5px 0` 与 `3px 10px 3px 0`，「位置」列 54px 右对齐 + `tabular-nums`，末列不留右边距 —— 修掉首版「16/28新闸路」黏连。
3. **键盘可达**：`:where(button, a, [tabindex]):focus-visible` 加 2px 蓝色描边。
4. **关掉 MapLibre 自带版权控件**：`attributionControl: false`。窄窗 876px 实测版权条 `[641,706,225,24]` 与页脚 `[0,708,876,20]` 重叠，用 CSS 抬高 `bottom` 会被 maplibre 自带样式压过；页脚胶囊已含「数据 © OpenStreetMap contributors（ODbL-1.0）」，合规信息不丢。

## S4-7 S4 自证（已完成）

```powershell
& E:
ode
pm.cmd run build      # 4.05 MB / 34 个文件
& E:
ode
pm.cmd run verify     # 21 项全过
```

浏览器端实测（876×740 窄窗，更严格）：21 层顺序正确、582+2+5=589 段、`line-color` 20 个 match 分支、点人民广场开抽屉、`Esc`/点空白都能关、hover 浮出「自然博物馆」、**glyph PBF 与字体文件各 0 次请求**、17 个资源 0 个 4xx、0 个 JS 错误。首屏未压缩 4.07 MB、gzip 后约 **0.90 MB**。

完整记录见 [`docs/validation-s4.md`](../docs/validation-s4.md)。

## S5-1 检索内核（已完成）

`lib/search.ts` 是纯函数、无 DOM、无第三方依赖，前端和测试脚本共用：

- `buildIndex(stations, lines)` → **450 条索引 = 430 站 + 20 线**
- `search(index, query, limit = 8)` → 命中项带 `kind / id / title / subtitle / dots / score`
- 匹配四类：中文（`人民`）、拼音全拼（`renmin`）、拼音首字母（`rmgc`）、英文与线路号（`people's square` / `2` / `line2` / `2haoxian`）
- 打分 120 / 110 / 96 / 88 / 74 / 58 分档；同分依次比 换乘站 → 线路数 → 名字长度 → id
- 拼音不引第三方库：`name_pinyin` 本身带声调（`ài guó lù`），NFD 去掉 `\p{M}` 后拼全拼与首字母

用例与性能（`scripts/test-search.mjs`）：22 条断言全过，**p50 0.037 ms / p95 0.077 ms / max 0.225 ms**。

## S5-2 搜索框（已完成）

`components/SearchBox.tsx` + `MapView` 的落地逻辑：

| 行为 | 实现 |
| --- | --- |
| 输入即搜 | 无防抖（索引 450 条，单次 <0.3 ms），但**中文输入法组合期间不检索** |
| IME 处理 | `compositionstart/end` 用 **ref** 而不是 state —— 组合开始与随后 `input` 事件可能同帧到达，state 未重渲染时闭包里读到的是旧值 |
| 选中站点 | 开抽屉 + `easeTo` 到站（z12.5） |
| 选中线路 | 先收抽屉，再按该线全部 segment 的 bbox `fitBounds` |
| Esc 分层 | 第一下只清搜索（输入框仍聚焦，可继续输入），第二下才失焦/关下拉 |
| 结果行 | 线路色点 + 站名 + 拼音 · 英文副行，命中片段 `<mark>` 高亮，线路结果显示「线路」徽标 |
| 无障碍 | `role=listbox/option`、`aria-expanded`、`aria-controls`、`aria-label` |
| 空态 | 「未找到「x」，试试站名、拼音首字母或线路号」 |

实测（1256×808）：搜索框 `448,16,360,34` 顶部居中；`lyl` → 龙阳路 + 龙耀路；`2号线` → 2 号线（含「线路」徽标）+ 12 号线；`xjh` → 徐家汇 (1)(2)(3)；`zzzz` → 空态；组合输入 `renmin` 期间下拉不出现、`compositionend` 后出「人民广场」；`Enter` 选中开抽屉；真实鼠标点线路结果 → 抽屉收起、`fitBounds` 到 2 号线（z10.57）。

修掉的两个真 bug（都是自己写的）：

1. **Esc 之后列表弹不出来** —— `setFocused(false)` 与 DOM 焦点不一致：输入框仍持有焦点，再 `focus()` 不触发 `onFocus`，于是「聚焦」状态永远为 false。改成 `active` 状态（聚焦或刚输入过即真）+ 外部点击时显式 `blur()`。
2. **IME 拼到一半就搜** —— `composing` 用 state，`compositionstart` 与紧随的 `input` 在同一帧时读到旧值；改 `composingRef`。

## S5-4 S5 自证（已完成）

```powershell
& E:\node\npm.cmd run test:search   # 22 条用例 + 性能断言
& E:\node\npm.cmd run build         # 4.06 MB / 34 个文件
& E:\node\npm.cmd run verify        # 21 项全过
```

浏览器端实测：搜索框顶部居中不压控件、`徐家` 出 3 条同名站、中文输入法组合期间不误触发、`Enter` 选中开抽屉、点线路结果框到整线并收抽屉、`Esc` 第一下只清搜索第二下才失焦。检索未引入任何运行时依赖，产物与 S4 持平（4.05 → 4.06 MB）。

完整记录见 [`docs/validation-s5.md`](../docs/validation-s5.md)。

## S6-1 子路径适配（已完成）

发布目标是 GitHub Pages 项目站点 `https://yukkki305.github.io/subways/`，
站点挂在 `/subways` 子路径下，因此构建必须带前缀，否则线上所有资源 404。

| 改动 | 位置 | 说明 |
| --- | --- | --- |
| `basePath: "/subways"` | `next.config.ts` | Next 自动给 `_next/` 资源加前缀 |
| `env.NEXT_PUBLIC_BASE_PATH` | `next.config.ts` | 供客户端代码拼接运行时 URL |
| `const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? ""` | `components/MapView.tsx` | 数据请求 `${BASE}/data/*.json`、worker `${BASE}/vendor/maplibre-gl-worker.mjs` |

**本地开发/预览地址随之变化**：`npm run dev` 与 `python -m http.server` 都要带 `/subways/`。

### 本地按子路径自测（已实测）

```powershell
# 把 out/ 放到子路径目录，再以父目录起静态服务
New-Item -ItemType Directory -Force E:\subway-data\s6test\subways | Out-Null
Copy-Item out\* E:\subway-data\s6test\subways\ -Recurse -Force
New-Item -ItemType File -Force E:\subway-data\s6test\subways\.nojekyll | Out-Null
python -m http.server 3210 --bind 127.0.0.1 -d E:\subway-data\s6test
# 打开 http://127.0.0.1:3210/subways/
```

实测结果（2026-11-03）：

| 项 | 结果 |
| --- | --- |
| 页面与资源 | 18 个请求，全部在 `/subways/` 下，**0 个 4xx** |
| 地图 | `loaded: true`、首屏 `zoom 9.59` |
| 图层计数 | `metro-line 582 + maglev 2 + apm 5 = 589`、`sea-fill 4`、`station-dot-transfer 80` |
| worker MIME | `text/javascript`（本地服务；Pages 上待 S6-3 复核） |
| 交互 | 点人民广场 → 抽屉「人民广场」正常 |
| `npm run verify` | 21 项全过，产物 4.06 MB |

截图：`E:\subway-data\preview\s6-1-subpath.png`。

### 发布时必须带 `.nojekyll`

`out/` 含 `_next/`、`_not-found/`、`__next.*.txt` 等下划线路径，GitHub Pages 默认跑 Jekyll 会
**忽略所有 `_` 开头的文件与目录** → JS/CSS 全 404、线上白屏。发布脚本必须在分支根目录写入空文件
`.nojekyll`（S6-2 落地，见 `docs/probe/s6-hosting.md` 第四节）。

## S6-2 发布流水线（已完成）

站点已上线：**https://yukkki305.github.io/subways/**

### 一条命令发布

```powershell
cd web
npm run deploy              # 构建 + 发布
npm run deploy -- --no-build # 复用现有 out/，只发布
npm run deploy -- --dry-run  # 只准备 staging，不推送
```

`web/scripts/deploy.mjs` 做的事：

1. `npm run build`（`--no-build` 跳过；构建链自带 `prebuild` 数据同步与 `postbuild` 死资产清理）
2. 把 `out/` 复制到 `%TEMP%\subways-pages`，写入空 **`.nojekyll`**，校验 `404.html` 存在
3. 在该目录 `git init -b gh-pages` + 提交（作者取仓库 `user.name`/`user.email`）
4. `git push --force origin gh-pages:gh-pages`，失败按 0/15/30/60/120 s 退避重试

**main 分支不受影响**：发布走临时仓库 + force push，`gh-pages` 每次都是完整快照，天然幂等。

### GitHub Pages 配置（已启用）

| 项 | 值 |
| --- | --- |
| URL | `https://yukkki305.github.io/subways/` |
| Source | branch `gh-pages`，path `/` |
| build_type | `legacy`（Jekyll 流程 + `.nojekyll` 短路） |
| HTTPS | 强制开启 |
| 首次构建 | commit `d26b9b4`，状态 `built`，耗时 **34.9 s** |

### 线上实测（2026-11-03）

| 项 | 结果 |
| --- | --- |
| `index.html` | 200 / 7,525 B / `<title>中国铁路图鉴 · 上海</title>` |
| 资源（js/css） | 200，`application/javascript`、`text/css` |
| `data/*.json` | 200，`application/json; charset=utf-8` |
| `*.geojson` | 200，**`application/geo+json`** |
| `vendor/maplibre-gl-worker.mjs` | 200，**`text/javascript`**（S6-0 的风险项已排除） |
| 浏览器 E2E | 18 个请求 **0 个 ≥400**；`zoom 9.59`；`metro-line 582 + maglev 2 + apm 5 = 589`、`sea-fill 4`、`station-dot-transfer 80` |
| 交互 | 点人民广场 → 抽屉「人民广场」；搜「陆家嘴」→ 2 条结果 |
| 未知路径 | 返回 404（Pages 用 `404.html`） |

截图：`E:\subway-data\preview\s6-2-live.png`。

### 已知边界

- 大陆访问速度未单独测（本机单请求最慢 1.17 s，属 Fastly 边缘节点正常范围）。
- `gh-pages` 分支不在 `main` 的历史里，看提交要切分支。
