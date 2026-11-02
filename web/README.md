# web：前端

Next.js 16（App Router + **静态导出**）渲染上海地铁图。数据全部来自仓库里的 `data/processed/`，构建前复制到 `public/data/`，前端不做运行时外部请求（AGENTS.md 第 3 节）。

## 命令

```powershell
$env:Path = 'E:\node;' + $env:Path      # 会话内工具进程可能继承旧环境
cd E:\subway\web
& E:\node\npm.cmd run dev               # 开发服务器 http://127.0.0.1:3210
& E:\node\npm.cmd run build             # 静态导出到 web\out\
& E:\node\npm.cmd run typecheck         # tsc --noEmit
```

看导出结果（`next start` 不适用于静态导出）：

```powershell
D:\python\python3.14.6\python.exe -m http.server 3210 --bind 127.0.0.1   # 在 web\out\ 下执行
```

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
| `components/` | 地图与交互组件（`MapView` / `StationPanel`，S3-3 起） |
| `lib/` | 地图样式、图层定义、数据加载（S3-3 起） |
| `scripts/sync-data.mjs` | 把 `../data/processed/shanghai/*` 复制到 `public/data/`（S3-2） |
| `public/data/` | 复制产物，**不进 git**（`.gitignore`） |
| `out/` | 静态导出结果，**不进 git** |

## 约定

- 客户端组件才碰 `window` / WebGL；地图初始化放 `useEffect` 或 `next/dynamic({ ssr: false })`
- 数据走 `fetch('/data/*.json')`，不要 `import` 进 bundle（1.8 MB 数据不该进 JS 包）
- 站点/线路的颜色一律取自 `lines.json` 的 `colour`，不在前端硬编码
