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

## 约定

- 客户端组件才碰 `window` / WebGL；地图初始化放 `useEffect` 或 `next/dynamic({ ssr: false })`
- 数据走 `fetch('/data/*.json')`，不要 `import` 进 bundle（1.8 MB 数据不该进 JS 包）
- 站点/线路的颜色一律取自 `lines.json` 的 `colour`，不在前端硬编码
