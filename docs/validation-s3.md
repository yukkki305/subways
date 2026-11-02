# S3 最小渲染纵切的验证记录

> 执行时间：2026-11-02。对应 `AGENTS.md` 第 12 节 P0 验收中「首屏可用，无控制台报错，静态导出可构建」一条。
> 环境：Windows + Node **26.13.0** / npm 11.20.0（`E:\node`）；Next **16.4.3**；React **19.3.1**；maplibre-gl **6.16.0**；数据快照 **20261101**。

## 1. 复现命令

```powershell
$env:Path = 'E:\node;' + $env:Path
cd E:\subway\web
& E:\node\npm.cmd run build        # 3.7 s，prebuild 自动同步数据
& E:\node\npm.cmd run verify       # 静态检查，20 项
D:\python\python3.14.6\python.exe -m http.server 3210 --bind 127.0.0.1   # 在 web\out\ 下执行
```

静态服务只为模拟「无 Next 运行时」的部署形态；真实托管需要开 gzip/brotli（下述体积按 gzip 另列）。

## 2. 静态检查（`web/scripts/verify-build.mjs`，20 项全过）

| 检查项 | 结果 |
| --- | --- |
| `index.html` 存在且含标题 | 通过（6,750 B） |
| 页面不引用任何外部站点资源 | 通过（只有同源） |
| 6 个数据文件齐全 | 通过 |
| 线路 20 条 | 通过 |
| 车站 430 座 | 通过 |
| 换乘 22 条 | 通过 |
| 区间 570 段 | 通过 |
| `meta.json` 计数与文件一致 | 通过（站 430 / 换乘候选 22） |
| `meta.json` 字节数与实际一致 | 通过（5 个文件） |
| 车站坐标都在 WGS-84 上海视野内 | 通过（430/430） |
| 线路颜色都是 6 位大写十六进制 | 通过（20/20） |
| `meta.json` 带 `as_of` | 通过（20261101） |
| `media/` 无 maplibre 副本残留 | 通过（只剩 `icon.*.svg`） |
| 无 `-dev.` 开发构建残留 | 通过（0 个） |
| 静态导出总体积 < 8 MB | 通过（3.96 MB / 34 个文件；全量 gzip 约 0.89 MB） |

清理前后的对比：构建产物 **9.10 MB → 3.96 MB**，释放 **5.14 MB**（7 个文件，见第 5 节第 1 条）。

## 3. 浏览器端 E2E（Edge，1256×808，CDP 真实鼠标/键盘事件）

| 断言 | 期望 | 实测 |
| --- | --- | --- |
| 地图初始化 | `map.loaded()` 为真 | 通过 |
| 首屏视野 | 覆盖全部 20 条线 | `zoom 9.59`、`center [121.442, 31.151]` |
| 画布尺寸 | 铺满容器 | 1256×808，无塌陷 |
| 图层顺序（底→顶） | 14 层固定 | `background / water-fill / coastline / water-line / district-line / province-line / metro-line-casing / metro-line / station-dot / station-dot-transfer / station-selected / station-hover-label / station-label-major / station-label-minor` |
| 线路渲染 | 570 段全部出图 | 渲染 589 个要素（含跨段拆分） |
| 线路配色 | 20 条都有颜色 | `line-color` 的 match 分支 = **20** |
| 换乘站在全城图可见 | 80 个 | 80 |
| 点击站点开抽屉 | 抽屉标题 = 站名 | 「人民广场」，3 个线路 chip，3 行站序 |
| `Esc` 关闭 | 抽屉消失 | 通过 |
| 点空白关闭 | 抽屉消失 | 通过 |
| 悬停浮出站名（z11.5） | hover 标签 1 个 | 「自然博物馆」 |
| 中文标签字形来源 | 不请求 glyph PBF | **0 次**（本机 TinySDF，符合 `AGENTS.md` 第 6 节） |
| 网络请求 | 无 4xx/5xx | 16 个资源全部 200 |
| JS 运行时错误 | 0 | 0（`error` / `unhandledrejection` / `console.error` 全挂监听） |
| maplibre 内部错误 | 0 | 0（`window.__mapErrors` 为空） |
| 页脚数据声明 | 线路数/站数/截止日期 | 「20 条线路 · 430 站 · 数据截止 20261101 · © OpenStreetMap contributors（ODbL-1.0）· 个人作品集项目，数据仅供参考」 |

## 4. 首屏载荷（关缓存，16 个请求 / 3.98 MB 未压缩）

| 资源 | 原始 | gzip |
| --- | ---: | ---: |
| `_next/static/chunks/09_tec-*.js`（含 maplibre-gl 本体） | 1,066,651 | 290,103 |
| `data/segment.geojson` | 860,829 | 106,203 |
| `vendor/maplibre-gl-worker.mjs` | 519,372 | 148,036 |
| `data/shanghai-basemap.geojson` | 495,983 | 136,809 |
| `data/station.json` | 441,120 | 33,308 |
| 其余 JS chunks（4 个） | 556,000 | ~110,000 |
| `lines.json` / `transfer.json` / `meta.json` | 61,115 | 9,672 |
| CSS（2 个） | 76,810 | ~14,000 |
| **合计** | **≈3.98 MB** | **≈0.75 MB** |

结论：首屏 gzip 后约 **0.75 MB**，其中 3 个数据文件（区间 + 底图 + 站点）占约 276 KB。P1 做全国时这个结构必须换（数据按城市切分、按需加载），但 P0 单城完全够用。

## 5. 已知问题（不阻塞 S3 完成）

1. **~~导出目录里有 3.69 MB 死资产~~ → 已修复**：`_next/static/media/` 下曾有 `maplibre-gl-dev.mjs`（2.49 MB）、`maplibre-gl-worker-dev.mjs`（1.20 MB）、`maplibre-gl.mjs`（1.11 MB）、`maplibre-gl-worker.mjs`（0.52 MB）、`maplibre-gl.css`（0.07 MB）与两个 0 字节 `*-shared*.mjs`，合计 5.14 MB，浏览器一个都不下载（worker 由 `setWorkerUrl("/vendor/…")` 指定）。
   处理：新增 `web/scripts/prune-build.mjs`，挂在 `postbuild` 上，删除 `media/` 下所有 `maplibre-gl*` 与 0 字节文件（`--all` 清空 media/、`--dry-run` 只报告）。
   **删光验证**：把 `out/` 复制到 `E:\subway-data\prunetest`、清空 `media/` 后起服务，`loaded` 为真、589 段线路、80 个换乘点、`__mapErrors` 为空 —— 证明这些文件确实是死资产。
   顺带补了 `web/app/icon.svg`，消掉最后一个 `favicon.ico` 404（清理后 E2E 的 4xx 为 **0**）。
2. **静态服务没有 gzip**：本次 `python -m http.server` 直出原始字节，所以「3.98 MB」是未压缩值；真实托管开 gzip 后约 0.75 MB。
3. **密集区标签仍有遮挡**：南京东路—外滩一带站距小，碰撞避让会让部分站名被吞（不是丢失，放大即出现）。
4. **没有英文站名**：`name_en` 数据齐备，界面未开；留给 S5 的检索/多语言开关。
5. **测试浏览器 HUD 干扰截图**：截图左上角的深色「DeepSeek」胶囊来自测试工具的覆盖层，不在页面 DOM 内，也不影响真实用户。

## 6. 对 P0 验收的贡献

`AGENTS.md` 第 12 节的 8 条验收中，本次直接覆盖：

- [x] 首屏可用，无控制台报错，静态导出可构建
- [ ] 页面能按城市/线路/站名检索（含拼音）—— **本次未做**，属 S5（检索与交互），本文件不覆盖

其余 6 条（线路数、坐标校验、颜色、换乘、站名比对、数据三问）在 S1/S2 阶段已有对应记录：`docs/validation-s2.md`、`docs/conflicts.md`、`data/README.md`。
