# S4 视觉与排版的验证记录

> 执行时间：2026-11-02。对应 `AGENTS.md` 第 12 节 P0 验收中「首屏可用，无控制台报错，静态导出可构建」一条的复检，以及 S4 六个子步骤（S4-1 字体、S4-2 英文站名、S4-3 制式线型、S4-4 海面、S4-5 站点符号、S4-6 排版终校）的逐项证据。
> 环境：Windows + Node **26.13.0** / npm 11.20.0（`E:\node`）；Next **16.4.3**；React **19.3.1**；maplibre-gl **6.16.0**；数据快照 **20261101**。
> 交互实测窗口 **876×740**（比 1256×808 更窄，属于更严格的排版测试）；1256×808 的版式另用 `captureBeyondViewport` 截图核对。

## 1. 复现命令

```powershell
$env:Path = 'E:\node;' + $env:Path
cd E:\subway\web
& E:\node\npm.cmd run build        # prebuild 同步数据 → next build → postbuild 清理死资产
& E:\node\npm.cmd run verify       # 静态检查，21 项，失败即 exit 1
D:\python\python3.14.6\python.exe -m http.server 3210 --bind 127.0.0.1   # 在 web\out\ 下执行
```

注意：静态服务占着 `out\` 时 `next build` 会报 `EBUSY: rmdir`，构建前先停服务。

## 2. 静态检查（`web/scripts/verify-build.mjs`，21 项全过）

| 检查项 | 结果 |
| --- | --- |
| `index.html` 存在且含标题 | 通过（7,035 B） |
| 页面不引用任何外部站点资源 | 通过（只有同源） |
| 7 个数据文件齐全（含 `sea.geojson`） | 通过 |
| 线路 20 条 / 车站 430 座 / 换乘 22 条 / 区间 570 段 | 通过 |
| `meta.json` 计数与文件一致 | 通过（站 430 / 换乘候选 22 / 1,949,717 B） |
| `meta.json` 字节数与实际一致 | 通过（6 个文件） |
| 车站坐标都在 WGS-84 上海视野内 | 通过（430/430） |
| 线路颜色都是 6 位大写十六进制 | 通过（20/20） |
| `meta.json` 带 `as_of` 与许可 | 通过（20261101） |
| `media/` 无 maplibre 副本残留 | 通过（只剩 `icon.*.svg`） |
| 无 `-dev.` 开发构建残留 | 通过（0 个） |
| 静态导出总体积 < 8 MB | 通过（**4.05 MB**，全量 gzip 约 0.91 MB） |

相比 S3-7 的 3.96 MB，增加 **0.09 MB**，即 S4-4 的海面（`shanghai-sea.geojson` 91,741 B）。

## 3. 浏览器端 E2E（Edge，876×740，CDP 真实鼠标/键盘事件）

| 断言 | 期望 | 实测 |
| --- | --- | --- |
| 地图初始化 | `map.loaded()` 为真 | 通过 |
| 首屏视野 | 覆盖全部 20 条线 | `zoom 9.15`（窄窗自适应）、`center [121.442, 31.148]` |
| 画布尺寸 | 铺满容器 | 876×740，无塌陷 |
| 图层数量与顺序 | 21 层固定（底→顶） | `background / sea-fill / water-fill / coastline / water-line / district-line / province-line / metro-line-casing / metro-line / maglev-line / apm-line / station-transfer-halo / station-dot / station-dot-transfer / station-selected / station-hover-label / station-label-major / station-label-minor / station-label-bilingual / station-label-long-zh / station-label-bilingual-long` |
| 制式分层计数 | 582 + 2 + 5 = 589 段 | `metro-line 582`、`maglev-line 2`、`apm-line 5`、`metro-line-casing 589` |
| 线路配色 | 20 条都有颜色 | `line-color` 的 match 分支 = **20** |
| 海面渲染 | 长江口/杭州湾/东海显色，岛屿是洞 | `sea-fill 4` 个要素（视野内） |
| 点击换乘站开抽屉 | 标题=站名，含全部线路 | 「人民广场」，3 个 chip（1/2/8 号线），3 行站序 |
| `Esc` 关闭 | 抽屉消失 | 通过 |
| 点空白关闭 | 抽屉消失 | 通过 |
| 悬停普通站（z11.6） | hover 标签浮出站名 | 「自然博物馆」，光标变 `pointer` |
| 中文/西文字形来源 | 不请求 glyph PBF、不请求字体文件 | **0 次 / 0 次**（本机 TinySDF + 系统字体栈，符合 `AGENTS.md` 第 6 节） |
| 网络请求 | 无 4xx/5xx | 17 个资源全部 200 |
| JS 运行时错误 | 0 | 0（`error` / `unhandledrejection` 全挂监听） |
| 版式（窄窗 876） | 页脚版权条不与任何控件重叠 | 通过（MapLibre 自带版权控件已关闭，版权统一进页脚胶囊） |
| 版式（宽窗 1256×808） | 标题/缩放控件/页脚不重叠 | 通过（`s4-6-wide-frame.png`） |

## 4. 首屏载荷（关缓存，17 个请求 / 4.07 MB 未压缩）

| 资源 | 原始 | gzip |
| --- | ---: | ---: |
| `_next/static/chunks/3oj766…js`（含 maplibre-gl 本体） | 1,069,257 | 290,679 |
| `data/segment.geojson` | 860,829 | 106,203 |
| `vendor/maplibre-gl-worker.mjs` | 519,372 | 148,036 |
| `data/shanghai-basemap.geojson` | 495,983 | 136,809 |
| `data/station.json` | 441,120 | 33,308 |
| 其余 JS chunks（6 个） | 465,888 | 135,396 |
| `data/sea.geojson` | 91,741 | 25,467 |
| CSS（2 个） | 77,087 | 12,057 |
| `lines.json` / `transfer.json` / `meta.json` | 61,264 | 9,697 |
| **合计** | **4,073,741（3.88 MiB）** | **897,582（0.86 MiB）** |

结论：首屏 gzip 后约 **0.90 MB**；数据文件（区间 + 底图 + 站点 + 海面）合计约 302 KB（gzip）。P1 做全国时必须改成按城市切分、按需加载，P0 单城仍够用。

## 5. 已知问题（不阻塞 S4 完成）

1. **长江口北支不出海色**：该水域在 OSM 里由河岸（`waterway=river`）围成、`coastline` 不闭合，若并入海面会把上海陆地一起吞掉（实测面积从 24,829 km² 跳到 37,793 km² 且人民广场落海）。当前取舍是「宁愿少一块海，不把陆地画成海」，判断口径与代价写在 `pipeline/14_extract_sea.py` 注释里。
2. **长英文名分两段出**：`name_en` 超过 30 字符的站（「一大会址·黄陂南路」的官方英文有 50+ 字符）在 z13–15 只出中文，z15 起才补英文，避免市中心整片折行。
3. **高缩放没有 hover 浮层**：`station-hover-label` 限定 `maxzoom 12.55`，更高缩放常驻站名已足够，重复浮层反而挡视线。
4. **密集区仍有标签被吞**：南京东路—外滩一带站距小，碰撞避让会隐藏部分站名，放大即出现（不是数据缺失）。
5. **测试浏览器 HUD 干扰截图**：截图左上角的深色「DeepSeek」胶囊来自测试工具覆盖层，不在页面 DOM 内。
6. **46 条关系仍未归属**（S1-6 遗留）：山东 39 条、南通 4 条、无站母关系 3 条，明细见 `docs/conflicts.md`。S4 未触碰这些数据。

## 6. 对 P0 验收的贡献

`AGENTS.md` 第 12 节的 8 条验收中，本次复检覆盖：

- [x] 首屏可用，无控制台报错，静态导出可构建
- [ ] 页面能按城市/线路/站名检索（含拼音）—— 仍未做，属 S5

其余 6 条（线路数、坐标校验、颜色、换乘、站名比对、数据三问）在 S1/S2 阶段已有记录：`docs/validation-s2.md`、`docs/conflicts.md`、`data/README.md`。
