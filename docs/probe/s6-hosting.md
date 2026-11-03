# S6-0 探测：托管与发布可行性

- 日期：2026-11-03
- 结论：**GitHub Pages 方案可行**，但有一个必须先处理的坑（Jekyll 忽略 `_` 开头的路径），对策是发布根目录放 `.nojekyll`
- 相关决策：D1=A（GitHub Pages）/ D2=A（项目站点 `/subways/`）/ D3=A（手动 `deploy`）/ D5=A（保持公开）

## 一、托管候选实测

| 目标 | 结果 | 判读 |
| --- | --- | --- |
| `api.github.com/repos/yukkki305/subways` | **200 / 0.76 s** | API 可用 |
| `api.github.com/repos/.../pages` | **404** | Pages **尚未启用**（不是权限问题） |
| `yukkki305.github.io/` | 404 / 0.91 s | 用户站点不存在（正常，本方案不依赖） |
| `yukkki305.github.io/subways/` | 404 / 0.78 s | 目标地址当前为空位 |
| `pages.github.com/` | 200 / 0.64 s | 服务本身可达 |
| `pages.cloudflare.com/` | 301 / 2.03 s | 备选可用 |
| `app.netlify.com/` | 200 / 1.01 s | 备选可用 |

仓库元数据（200 响应）：

| 字段 | 值 |
| --- | --- |
| `private` / `visibility` | `false` / `public` |
| `default_branch` | `main` |
| `has_pages` | `false` |
| `size` | 912 KB |
| `license` | `null`（无 LICENSE 文件，见「遗留」） |
| 现有分支 | 仅 `main` |

## 二、发布权限

从 Windows 凭据管理器读取的 token（`gho_`，40 字符，未打印）实测：

- 响应头 `X-OAuth-Scopes: gist, repo, workflow`
- `X-RateLimit-Remaining: 4999`

`repo` 是 classic PAT 里启用 Pages 所需的 scope（细粒度 token 则需要 Pages:write + Administration:write）。
因此 **`POST /repos/yukkki305/subways/pages` 具备调用条件**，S6-2 可直接用 API 启用 Pages。

## 三、CDN 延迟（`yukkki305.github.io`）

| 采样 | TTFB | 总耗时 | HTTP |
| --- | --- | --- | --- |
| 1 | 0.65 s | 0.91 s | 1.1 |
| 2 | 0.46 s | 0.47 s | 1.1 |
| 3 | 0.51 s | 0.51 s | 1.1 |

DNS：`185.199.108.153 / .109 / .110 / .111`（GitHub Pages 标准四条 A 记录，Fastly）。

判读：**远低于「>10 s 首屏即停」的触发器**，可用。注意这只是 404 页面，真实站点还要加载 4 MB 资源，
S6-3 必须以真实首屏为准复测。

## 四、★ 关键风险：Jekyll 会忽略 `_` 开头的路径

`web/out/` 顶层实际内容：

```
404  data  vendor  _next  _not-found  404.html  icon.svg  index.html  index.txt
__next._full.txt  __next._tree.txt  __next.__PAGE__.txt
```

`index.html` 里的资源引用是**绝对路径**：

```
href="/_next/static/chunks/10gxj3dn5tlu8.css"
src="/_next/static/chunks/2l_0m1ybyhq2o.js"
```

GitHub Pages 的「Deploy from a branch」默认跑 Jekyll，而 **Jekyll 会忽略所有以 `_` 开头的文件与目录**
（`_next/`、`_not-found/`、`__next.*.txt` 全部中招）。后果是 JS/CSS 全部 404，线上白屏。

**对策（S6-1/S6-2 必做）**：发布分支根目录放一个空的 **`.nojekyll`** 文件。
这个文件必须在 `out/` 之外单独准备（Next 不会生成它），发布脚本要显式写入。

## 五、路径前缀（D2=A 的直接后果）

项目站点地址是 `https://yukkki305.github.io/subways/`，而资源引用是 `/_next/...`（指向根）。
因此 S6-1 必须设 `basePath: "/subways"` + `assetPrefix: "/subways/"`，否则线上所有静态资源 404。

## 六、产物现状（发布基线）

| 项 | 值 |
| --- | --- |
| 文件数 | 35 |
| 总体积 | 4,254,737 B（4.06 MB） |
| gzip 后 | ≈ 0.92 MB（S4-7 实测 897,582 B） |
| 单文件上限 | 无超标；最大为 `_next/static/chunks/*.js` 约 1 MB |
| GitHub Pages 限制 | 仓库 1 GB / 月流量 100 GB / 每小时构建 10 次 → **当前量级完全够用** |

## 七、尚未验证、留到 S6-3 的项

1. `.mjs`（`/vendor/maplibre-gl-worker.mjs`）在 Pages 上的 MIME 是否为 `text/javascript` —— 若不是，worker 会因 MIME 被拒而地图空白。
2. `.geojson` 的 MIME（`fetch` 不校验，风险低，但仍记录）。
3. 真实首屏耗时（4 MB 资源 + 首次渲染）。
4. 404 页面：Next 导出的 `404.html` 在 Pages 上是否被正确用于未知路径。

## 八、遗留（需在 S6-4 一并处理）

- 仓库 **没有 LICENSE**。项目定位是作品集且数据为 ODbL，建议加 `LICENSE`（代码用 MIT，数据另注 ODbL），否则外人无法判断可否复用。
- `has_pages = false`，S6-2 首次启用后需回填本文件。
