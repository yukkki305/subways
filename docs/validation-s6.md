# S6-3 线上自证

> 站点：<https://yukkki305.github.io/subways/>
> 记录日期：2026-11-03
> 执行方式：本机（Windows + Edge 1256×808）以工程脚本与 CDP 驱动校验，非大陆探针

## 1. 复现命令

```powershell
cd web
npm run deploy                  # 构建 + 发布（会覆盖 gh-pages）
curl.exe -s -o NUL -w "%{http_code} %{size_download}\n" https://yukkki305.github.io/subways/
```

## 2. 二次部署幂等性

| 轮次 | gh-pages 提交 | staging 文件数 | staging 字节 | Pages 构建耗时 |
| --- | --- | --- | --- | --- |
| 首次（S6-2） | `d26b9b4` | 36 | 4,255,957 | 34,874 ms |
| 二次 | `b220254` | 36 | 4,255,957 | 27,487 ms |
| 三次（窄屏修复） | `82dc875` | 36 | 4,255,957 | 23,547 ms |

文件清单逐条比对：**只差 3 个文件**，全部位于 `_next/static/<buildId>/`（`_buildManifest.js`、`_clientMiddlewareManifest.js`、`_ssgManifest.js`）——`buildId` 每次构建都变。旧 `buildId` 目录**整体消失、不残留**，因此：

- 发布是**快照替换**，不是增量叠放；
- 重复执行 `npm run deploy` 结果一致，幂等成立。

## 3. 线上 HTTP 复核

| 路径 | 状态 | Content-Type |
| --- | --- | --- |
| `/subways/` | 200 / 7,525 B | `text/html` |
| `_next/static/chunks/*.js` | 200 | `application/javascript; charset=utf-8` |
| `_next/static/chunks/*.css` | 200 | `text/css; charset=utf-8` |
| `data/station.json`、`data/meta.json` | 200 | `application/json; charset=utf-8` |
| `data/segment.geojson`、`data/sea.geojson` | 200 | `application/geo+json` |
| `vendor/maplibre-gl-worker.mjs` | 200 / 519,372 B | `text/javascript; charset=utf-8` |
| `/subways/does-not-exist/` | 404 | `text/html`（`404.html`） |

`.mjs` 的 MIME 是 S6-0 列出的最大风险项（错误类型会让 worker 直接被拒），线上实测为 `text/javascript`，风险解除。

## 4. 桌面端 E2E（1256×808）

| 项 | 结果 |
| --- | --- |
| 资源请求 | 17 个，**0 个 ≥400** |
| 导航计时 | TTFB **337 ms** / DOMContentLoaded 349 ms / load 417 ms |
| 首屏相机 | `zoom 9.59`、`center [121.442, 31.151]` |
| 线段计数 | `metro-line 582 + maglev-line 2 + apm-line 5 = 589`、`metro-line-casing 589` |
| 其它图层 | `sea-fill 4`、`station-dot-transfer 80`、`district-line 26`、`water-line 8` |
| 点击 | 点人民广场 → 抽屉「人民广场」+ 3 个线路 chip |
| 键盘 | `Escape` → 抽屉关闭 |
| 搜索 | 输入「陆家嘴」→ 2 条结果（陆家嘴(1)/(2)，各带线路色点） |

## 5. 窄屏与响应式

| 视口 | 关键几何 | 结论 |
| --- | --- | --- |
| 852×780 | 标题 `[16,16,163,35]`、搜索框 `[246,16,360,34]`、页脚 `[0,748,852,20]` | 不重叠、无横向溢出、版权控件已移除（`null`） |
| 696×700（修复前） | 搜索框 `[16,16,664,34]` 与标题**重叠** | ❌ 真 bug |
| 696×740（修复后） | 搜索框 `[16,60,664,34]`，标题 `[16,16,163,35]`，下拉 `[16,102,664,58]` | ✅ 不重叠、无横向溢出 |

**修复内容**：`app/globals.css` 的 `@media (max-width: 760px)` 给 `.search` 加 `top: 60px`，让搜索框落到标题下方整行（原来 `top:16` 会压住标题）。

截图：`s6-2-live.png`（桌面）、`s6-3-narrow.png`（696px，搜索下拉展开）。

## 6. 已知边界

1. **大陆访问速度未在真机测**：上表 TTFB 337 ms 是本机（非大陆网络）视角，只能说明站点与资源可用，不能作为大陆体感结论。如需，请你在常用网络下点开一次；若首屏 >10 s 则触发 S6 的失败触发器。
2. **首次访问冷启动**：Pages 首次构建完成前访问会 404，属正常（本项目构建耗时 23–35 s）。
3. **`gh-pages` 不在 `main` 历史里**：站点快照是独立分支，`git log` 需切分支查看。
4. **窄屏只覆盖到 696px**：更极端宽度（<480px）未单独验证，属后续优化项。
5. **数据截止 2026-11-01**：线上页面显示的时间戳是快照时间，不是构建时间。

## 7. 与 `AGENTS.md` §12 的关系

本步只验证「P0 成果对外可访问」，不改变 §12 的验收口径。九项验收的逐条签字放在 S6-4（`docs/acceptance-p0.md`）。
