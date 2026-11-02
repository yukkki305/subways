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
& E:\node\npm.cmd run verify            # 构建自证：20 项静态检查（S3-7，含打包残留）
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

## S3-7 构建自证（已完成）

`scripts/verify-build.mjs` 只做静态检查，不启浏览器，任何机器可重跑：

```powershell
& E:\node\npm.cmd run build
& E:\node\npm.cmd run verify      # 20 项，失败即 exit 1
```

覆盖：入口 HTML、无外部资源、6 个数据文件齐全、20 线/430 站/22 换乘/570 段、`meta.json` 计数与字节数自洽、车站坐标全在 WGS-84 上海视野内（防 GCJ-02 混入）、颜色为合法十六进制、总体积上限。

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
